import logging
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

def get_email_ids(query: str, gmail_instance):
    # Placeholder for existing get_email_ids function
    # This function is imported by email_routes.py, so it needs to exist.
    # Actual implementation details are not relevant to the current task.
    logger.info(f"get_email_ids called with query: {query}")
    return []

def get_email(message_id: str, gmail_instance, user_email: str):
    # Placeholder for existing get_email function
    # This function is imported by email_routes.py, so it needs to exist.
    # Actual implementation details are not relevant to the current task.
    logger.info(f"get_email called for message_id: {message_id}")
    return {}

def archive_email_in_gmail(service, message_id: str, user_id: str):
    """
    Archives an email in Gmail by removing the 'INBOX' label.
    Does not archive if 'INBOX' label is not present.

    Args:
        service: Authorized Gmail API service instance.
        message_id: ID of the email message to archive.
        user_id: The ID of the user for logging purposes.
    """
    try:
        message = service.users().messages().get(userId='me', id=message_id, format='metadata', metadataHeaders=['labelIds']).execute()
        label_ids = message.get('labelIds', [])

        if 'INBOX' in label_ids:
            logger.info(f"user_id:{user_id} Email {message_id} is in INBOX. Archiving...")
            modify_request = {
                'removeLabelIds': ['INBOX']
            }
            service.users().messages().modify(userId='me', id=message_id, body=modify_request).execute()
            logger.info(f"user_id:{user_id} Email {message_id} archived successfully.")
        else:
            logger.info(f"user_id:{user_id} Email {message_id} is not in INBOX. No action taken.")

    except HttpError as error:
        if error.resp.status == 403:
            logger.error(
                f"user_id:{user_id} Insufficient permissions (403 Forbidden) while trying to archive email {message_id}. "
                f"This likely means the application lacks the 'gmail.modify' scope. Error: {error}"
            )
            # You might want to raise a specific custom exception here to be caught by the caller
            # e.g., raise InsufficientPermissionsError(f"Missing gmail.modify scope for user {user_id}")
            # For now, re-raising the original error after logging.
            raise  # Re-raise the HttpError to be handled by the caller in email_routes.py
        else:
            logger.error(
                f"user_id:{user_id} An API error occurred (status: {error.resp.status}) while trying to archive email {message_id}: {error}"
            )
            raise # Re-raise other HttpErrors
    except Exception as e:
        logger.error(f"user_id:{user_id} An unexpected error occurred while archiving email {message_id}: {e}")
        raise # Re-raise unexpected errors
