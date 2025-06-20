from utils import auth_utils
from unittest import mock
import json # Moved import json to the top
from datetime import datetime

from fastapi import Request
from sqlalchemy.orm import Session
from google.oauth2.credentials import Credentials

from db.users import Users
from db.processing_tasks import TaskRuns, FINISHED, STARTED
from routes.email_routes import fetch_emails_to_db


def test_processing(db_session, client, logged_in_user):
    db_session.add(TaskRuns(user=logged_in_user, status=STARTED))
    db_session.flush()

    # make request to check on processing status
    resp = client.get("/processing", follow_redirects=False)

    # assert response
    assert resp.status_code == 200, resp.headers
    assert resp.json()["processed_emails"] == 0


def test_processing_404(db_session, client, logged_in_user):
    resp = client.get("/processing", follow_redirects=False)
    assert resp.status_code == 404


def test_fetch_emails_to_db(db_session: Session):
    test_user_id = "123"

    db_session.add(
        Users(
            user_id=test_user_id,
            user_email="user123@example.com",
            start_date=datetime(2000, 1, 1),
        )
    )
    db_session.commit()

    with mock.patch("routes.email_routes.get_email_ids"):
        fetch_emails_to_db(
            auth_utils.AuthenticatedUser(Credentials("abc")),
            Request({"type": "http", "session": {}}),
            user_id=test_user_id,
        )

    task_run = db_session.get(TaskRuns, test_user_id)
    assert task_run.status == FINISHED


def test_fetch_emails_to_db_in_progress_rate_limited_no_processing(db_session: Session):
    test_user_id = "123"

    user = Users(
        user_id=test_user_id,
        user_email="user123@example.com",
        start_date=datetime(2000, 1, 1),
    )
    db_session.add(user)
    db_session.add(TaskRuns(user=user, status=STARTED))
    db_session.commit()

    with mock.patch("routes.email_routes.get_email_ids") as mock_get_email_ids:
        fetch_emails_to_db(
            auth_utils.AuthenticatedUser(Credentials("abc")),
            Request({"type": "http", "session": {}}),
            user_id=test_user_id,
        )

    mock_get_email_ids.assert_not_called()
    task_run = db_session.get(TaskRuns, test_user_id)
    assert task_run.status == STARTED


def test_fetch_emails_to_db_with_interview_invitation(db_session: Session, mocker):
    test_user_id = "user_interview_test"
    test_email_id = "email_interview_id"
    company_name_from_llm = "FutureTech Inc."
    mock_briefing_json = '{"company_info": "Details about FutureTech Inc."}'

    # 1. Setup User
    db_session.add(
        Users(
            user_id=test_user_id,
            user_email="interview_user@example.com",
            start_date=datetime(2023, 1, 1),
        )
    )
    # TaskRuns is created by fetch_emails_to_db if not exists, or updated.
    # Ensure it starts fresh or in a state that allows processing.
    existing_task_run = db_session.get(TaskRuns, test_user_id)
    if existing_task_run:
        db_session.delete(existing_task_run)
    db_session.commit()


    # 2. Mock external calls & helpers
    mock_get_email_ids = mocker.patch("routes.email_routes.get_email_ids")
    mock_get_email = mocker.patch("routes.email_routes.get_email")
    mock_process_email = mocker.patch("routes.email_routes.process_email")
    mock_generate_briefing = mocker.patch("routes.email_routes.generate_interview_briefing")
    mock_create_user_email = mocker.patch("routes.email_routes.create_user_email")

    # Setup return values for mocks
    mock_get_email_ids.return_value = [{"id": test_email_id, "threadId": "thread1"}] # Must be a list of dicts
    mock_get_email.return_value = {
        "id": test_email_id,
        "text_content": "Your interview is scheduled.",
        "date": "Tue, 20 Jun 2023 10:00:00 +0000",
        "subject": "Interview Invitation",
        "from": "hr@futuretech.com",
    }
    mock_process_email.return_value = {
        "company_name": company_name_from_llm,
        "job_application_status": "Interview invitation", # Critical for triggering briefing
        "job_title": "Software Engineer",
    }
    mock_generate_briefing.return_value = json.loads(mock_briefing_json) # generate_interview_briefing returns a dict

    # create_user_email returns a UserEmails object, or None. Mock it to return a dummy object.
    mock_user_email_instance = mock.MagicMock()
    mock_create_user_email.return_value = mock_user_email_instance


    # 3. Prepare arguments for fetch_emails_to_db
    mock_user_creds = Credentials("dummy_token")
    authenticated_user = auth_utils.AuthenticatedUser(mock_user_creds)
    # Ensure user_id is part of AuthenticatedUser as per create_user_email usage
    authenticated_user.user_id = test_user_id
    authenticated_user.user_email = "interview_user@example.com"


    mock_request_session = {
        "is_new_user": False, # Assuming not a new user for simplicity
        "start_date": "01/01/2023"
    }
    mock_request = Request({"type": "http", "session": mock_request_session, "user": authenticated_user})


    # 4. Call the function
    fetch_emails_to_db(
        user=authenticated_user,
        request=mock_request,
        user_id=test_user_id
    )

    # 5. Assertions
    mock_get_email_ids.assert_called_once()
    mock_get_email.assert_called_once_with(message_id=test_email_id, gmail_instance=mocker.ANY, user_email=authenticated_user.user_email)
    mock_process_email.assert_called_once_with("Your interview is scheduled.")

    # Assert generate_interview_briefing was called
    mock_generate_briefing.assert_called_once_with(company_name_from_llm, []) # Empty list for interviewer_names

    # Assert create_user_email was called with the briefing
    mock_create_user_email.assert_called_once()
    call_args_for_create_user_email = mock_create_user_email.call_args[0] # Get positional arguments

    passed_user_object = call_args_for_create_user_email[0]
    passed_message_data = call_args_for_create_user_email[1]

    assert passed_user_object.user_id == test_user_id
    assert passed_message_data["company_name"] == company_name_from_llm
    assert passed_message_data["application_status"] == "Interview invitation"
    assert passed_message_data["interview_briefing"] == mock_briefing_json # generate_interview_briefing returns a dict, but it's stored as JSON string

    # Check that the task status is updated to FINISHED
    task_run = db_session.get(TaskRuns, test_user_id)
    assert task_run is not None
    assert task_run.status == FINISHED
    assert task_run.processed_emails == 1
    assert task_run.total_emails == 1

    # Ensure db_session.add_all was called with the email record from create_user_email
    # This requires inspecting db_session's add_all or commit, which can be tricky.
    # However, since create_user_email is mocked, we trust it was called correctly.
    # And we check the task_run status which implies commits happened.
    # If create_user_email was not mocked, we'd check db_session.get(UserEmails, ...)
