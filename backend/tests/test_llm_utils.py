import pytest
import json
from unittest.mock import patch, MagicMock, ANY # Added ANY
from backend.utils.llm_utils import generate_interview_briefing, model as llm_model_instance
from google.ai.generativelanguage_v1beta2 import GenerateTextResponse # Corrected import

# Default successful LLM response for the main briefing
DEFAULT_LLM_BRIEFING_TEXT = json.dumps({
    "company_info": {"description": "Default company description."},
    "company_talking_points": ["Default company talking point."],
    "interviewers": []
})

class TestGenerateInterviewBriefing:

    @pytest.fixture(autouse=True)
    def common_mocks_autouse(self, mocker):
        # Automatically mock time.sleep for all tests in this class
        mocker.patch('time.sleep')
        # Mock settings for API keys, can be overridden per test
        mock_settings = mocker.patch('backend.utils.llm_utils.settings')
        mock_settings.GOOGLE_API_KEY = "fake_google_key"
        mock_settings.APIFY_API_KEY = "fake_apify_key" # Default to having Apify key
        return mock_settings

    # Helper to set up ApifyClient mock structure
    def _setup_mock_apify_client(self, mocker, client_constructor_mock):
        mock_apify_instance = MagicMock()
        client_constructor_mock.return_value = mock_apify_instance

        mock_actor_instance = MagicMock()
        mock_apify_instance.actor.return_value = mock_actor_instance

        mock_actor_call_result = MagicMock()
        # Configure .get for typical id/defaultDatasetId access
        mock_actor_call_result.get.side_effect = lambda key, default=None: {"id": "run_id", "defaultDatasetId": "dataset_id"}.get(key, default)
        mock_actor_instance.call.return_value = mock_actor_call_result

        mock_dataset_instance = MagicMock()
        mock_apify_instance.dataset.return_value = mock_dataset_instance
        mock_dataset_instance.iterate_items.return_value = [] # Default to no items

        return mock_apify_instance # Return the main instance for further specific actor mocking if needed

    # --- Tests for Apify Integration ---

    @patch('backend.utils.llm_utils.ApifyClient')
    @patch.object(llm_model_instance, 'generate_content')
    def test_apify_disabled_if_no_api_key(self, mock_llm_generate_content, mock_apify_client_constructor, common_mocks_autouse):
        common_mocks_autouse.APIFY_API_KEY = None # Override: No Apify key

        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = DEFAULT_LLM_BRIEFING_TEXT
        mock_llm_generate_content.return_value = mock_llm_briefing_response # Only one LLM call (main briefing)

        result = generate_interview_briefing("NoApifyCorp")

        mock_apify_client_constructor.assert_not_called()
        mock_llm_generate_content.assert_called_once() # No LLM call for URL search
        prompt_arg = mock_llm_generate_content.call_args[0][0]
        assert "Apify related searches will be skipped" in prompt_arg
        assert "(Simulated)" in prompt_arg # Ensure fallback to simulated data
        assert result == json.loads(DEFAULT_LLM_BRIEFING_TEXT)

    @patch('backend.utils.llm_utils.ApifyClient')
    @patch.object(llm_model_instance, 'generate_content')
    def test_apify_client_initialization_fails(self, mock_llm_generate_content, mock_apify_client_constructor, common_mocks_autouse, mocker):
        mock_logger = mocker.patch('backend.utils.llm_utils.logger')
        mock_apify_client_constructor.side_effect = Exception("Apify client init error")

        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = DEFAULT_LLM_BRIEFING_TEXT
        mock_llm_generate_content.return_value = mock_llm_briefing_response

        generate_interview_briefing("InitFailCorp")

        mock_logger.error.assert_any_call("Failed to initialize ApifyClient: Apify client init error")
        mock_llm_generate_content.assert_called_once()
        prompt_arg = mock_llm_generate_content.call_args[0][0]
        assert "Apify related searches will be skipped" not in prompt_arg # It tries, then logs error, then default prompt for company
        assert "(Simulated) Search for major news" in prompt_arg # Check for default company prompt part

    @patch('backend.utils.llm_utils.ApifyClient')
    @patch.object(llm_model_instance, 'generate_content')
    def test_llm_finds_company_url_apify_company_actor_no_data(self, mock_llm_generate_content, mock_apify_client_constructor, common_mocks_autouse, mocker):
        mock_apify_instance = self._setup_mock_apify_client(mocker, mock_apify_client_constructor)
        # mock_apify_instance.dataset.return_value.iterate_items is already set to [] by helper

        mock_llm_url_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_url_response.text = "https://www.linkedin.com/company/testcorpllc"
        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = DEFAULT_LLM_BRIEFING_TEXT
        mock_llm_generate_content.side_effect = [mock_llm_url_response, mock_llm_briefing_response]

        generate_interview_briefing("TestCorpLLC")

        assert mock_llm_generate_content.call_count == 2
        mock_apify_instance.actor.assert_called_with("pocesar/linkedin-company-scraper") # Placeholder
        mock_apify_instance.actor.return_value.call.assert_called_with(run_input={"linkedin_urls": ["https://www.linkedin.com/company/testcorpllc"], "max_pages_to_scrape": 1})

        final_prompt_for_briefing = mock_llm_generate_content.call_args_list[1][0][0]
        assert "No data returned by Apify company actor" in final_prompt_for_briefing

    @patch('backend.utils.llm_utils.ApifyClient')
    @patch.object(llm_model_instance, 'generate_content')
    def test_apify_company_data_success_no_interviewers(self, mock_llm_generate_content, mock_apify_client_constructor, common_mocks_autouse, mocker):
        mock_apify_instance = self._setup_mock_apify_client(mocker, mock_apify_client_constructor)
        mock_company_apify_data = {"description": "Real company data from Apify.", "industry": "Tech"}
        mock_apify_instance.dataset.return_value.iterate_items.return_value = [mock_company_apify_data]

        mock_llm_url_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_url_response.text = "https://www.linkedin.com/company/testcorp"
        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = DEFAULT_LLM_BRIEFING_TEXT
        mock_llm_generate_content.side_effect = [mock_llm_url_response, mock_llm_briefing_response]

        generate_interview_briefing("TestCorp")

        assert mock_llm_generate_content.call_count == 2
        final_prompt_for_briefing = mock_llm_generate_content.call_args_list[1][0][0]
        assert "Real company data from Apify." in final_prompt_for_briefing
        assert "Industry: Tech" in final_prompt_for_briefing

    @patch('backend.utils.llm_utils.ApifyClient')
    @patch.object(llm_model_instance, 'generate_content')
    def test_apify_interviewer_data_success_company_data_fails(self, mock_llm_generate_content, mock_apify_client_constructor, common_mocks_autouse, mocker):
        mock_apify_instance = self._setup_mock_apify_client(mocker, mock_apify_client_constructor)
        mock_interviewer_apify_data = {"profile_url": "linkedin.com/in/johndoe", "headline": "Manager at TestCorp"}

        # This configures the mock ApifyClient's dataset().iterate_items() for *all* subsequent calls through this instance
        # First call (company) returns [], second call (interviewer) returns data
        mock_apify_instance.dataset.return_value.iterate_items.side_effect = [
            [],  # For company actor call
            [mock_interviewer_apify_data]  # For interviewer actor call
        ]

        mock_llm_url_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_url_response.text = "https://linkedin.com/company/testcorp" # Company URL found
        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = DEFAULT_LLM_BRIEFING_TEXT
        mock_llm_generate_content.side_effect = [mock_llm_url_response, mock_llm_briefing_response]

        generate_interview_briefing("TestCorp", interviewer_names=["John Doe"])

        assert mock_llm_generate_content.call_count == 2
        mock_apify_instance.actor.assert_any_call("pocesar/linkedin-company-scraper")
        mock_apify_instance.actor.assert_any_call("harvestapi/linkedin-profile-search")

        final_prompt_for_briefing = mock_llm_generate_content.call_args_list[1][0][0]
        assert "No data returned by Apify company actor" in final_prompt_for_briefing
        assert "Manager at TestCorp" in final_prompt_for_briefing # Interviewer data present

    @patch('backend.utils.llm_utils.ApifyClient')
    @patch.object(llm_model_instance, 'generate_content')
    def test_full_apify_success_company_and_interviewers(self, mock_llm_generate_content, mock_apify_client_constructor, common_mocks_autouse, mocker):
        mock_apify_instance = self._setup_mock_apify_client(mocker, mock_apify_client_constructor)
        mock_company_apify_data = {"description": "Awesome Corp data.", "industry": "Innovation"}
        mock_interviewer_apify_data = {"profile_url": "linkedin.com/in/innovator", "headline": "Lead Innovator @ AwesomeCorp"}

        mock_apify_instance.dataset.return_value.iterate_items.side_effect = [
            [mock_company_apify_data],
            [mock_interviewer_apify_data]
        ]

        mock_llm_url_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_url_response.text = "https://linkedin.com/company/awesomecorp"
        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = DEFAULT_LLM_BRIEFING_TEXT # LLM synthesizes this
        mock_llm_generate_content.side_effect = [mock_llm_url_response, mock_llm_briefing_response]

        generate_interview_briefing("AwesomeCorp", interviewer_names=["Innovator Person"])

        assert mock_llm_generate_content.call_count == 2
        final_prompt_for_briefing = mock_llm_generate_content.call_args_list[1][0][0]
        assert "Awesome Corp data." in final_prompt_for_briefing
        assert "Industry: Innovation" in final_prompt_for_briefing
        assert "Lead Innovator @ AwesomeCorp" in final_prompt_for_briefing

    @patch('backend.utils.llm_utils.ApifyClient')
    @patch.object(llm_model_instance, 'generate_content')
    def test_llm_fails_to_find_company_url_fallback(self, mock_llm_generate_content, mock_apify_client_constructor, common_mocks_autouse, mocker):
        mock_apify_instance = self._setup_mock_apify_client(mocker, mock_apify_client_constructor)

        mock_llm_url_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_url_response.text = "NOT_FOUND" # LLM indicates URL not found
        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = DEFAULT_LLM_BRIEFING_TEXT
        mock_llm_generate_content.side_effect = [mock_llm_url_response, mock_llm_briefing_response]

        generate_interview_briefing("UnknownCorp")

        assert mock_llm_generate_content.call_count == 2
        # Verify company scraper actor was NOT called
        called_actors = [call[0][0] for call in mock_apify_instance.actor.call_args_list]
        assert "pocesar/linkedin-company-scraper" not in called_actors

        final_prompt_for_briefing = mock_llm_generate_content.call_args_list[1][0][0]
        assert "Skipping Apify company data fetch as no LinkedIn URL was obtained" in final_prompt_for_briefing

    @patch('backend.utils.llm_utils.ApifyClient')
    @patch.object(llm_model_instance, 'generate_content')
    def test_apify_company_actor_call_fails(self, mock_llm_generate_content, mock_apify_client_constructor, common_mocks_autouse, mocker):
        mock_apify_instance = self._setup_mock_apify_client(mocker, mock_apify_client_constructor)

        # Make the company actor's call() method raise an exception
        mock_apify_instance.actor.return_value.call.side_effect = Exception("Apify company actor exploded")
        # This will apply to the first actor call, which is company search after URL is found by LLM.

        mock_llm_url_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_url_response.text = "https://www.linkedin.com/company/explodecorp"
        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = DEFAULT_LLM_BRIEFING_TEXT
        mock_llm_generate_content.side_effect = [mock_llm_url_response, mock_llm_briefing_response]

        generate_interview_briefing("ExplodeCorp")

        assert mock_llm_generate_content.call_count == 2
        final_prompt_for_briefing = mock_llm_generate_content.call_args_list[1][0][0]
        assert "Error during Apify company data call" in final_prompt_for_briefing

    # --- Tests for basic LLM functionality (adapted from previous set) ---

    @patch.object(llm_model_instance, 'generate_content')
    def test_main_llm_returns_malformed_json_apify_off(self, mock_llm_generate_content, common_mocks_autouse):
        common_mocks_autouse.APIFY_API_KEY = None # Apify is off for this test

        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = "This is not JSON"
        mock_llm_generate_content.return_value = mock_llm_briefing_response # Only one LLM call (main)

        result = generate_interview_briefing("MalformedCorp")

        assert "error" in result
        assert "Failed to parse JSON response" in result["error"]
        # Main LLM call for briefing retries 3 times
        assert mock_llm_generate_content.call_count == 3

    @patch.object(llm_model_instance, 'generate_content')
    def test_main_llm_api_call_failure_rate_limit_apify_off(self, mock_llm_generate_content, common_mocks_autouse, mocker):
        common_mocks_autouse.APIFY_API_KEY = None # Apify is off
        mock_sleep = mocker.patch('time.sleep') # Already auto-mocked by fixture, but can grab it here for asserts

        mock_llm_generate_content.side_effect = Exception("429 Resource has been exhausted")

        result = generate_interview_briefing("RateLimitCorp")

        assert "error" in result
        assert "Failed to generate interview briefing after 3 attempts" in result["error"]
        assert mock_llm_generate_content.call_count == 3
        assert mock_sleep.call_count == 2

    @patch.object(llm_model_instance, 'generate_content')
    def test_main_llm_api_call_other_exception_apify_off(self, mock_llm_generate_content, common_mocks_autouse):
        common_mocks_autouse.APIFY_API_KEY = None

        mock_llm_generate_content.side_effect = Exception("Some other API error")

        result = generate_interview_briefing("ExceptionCorp")

        assert "error" in result
        assert "An unexpected error occurred: Some other API error" in result["error"]
        assert mock_llm_generate_content.call_count == 1 # No retries for this type of error

    @patch.object(llm_model_instance, 'generate_content')
    def test_main_llm_returns_empty_response_text_apify_off(self, mock_llm_generate_content, common_mocks_autouse):
        common_mocks_autouse.APIFY_API_KEY = None

        mock_llm_briefing_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_briefing_response.text = ""
        mock_llm_generate_content.return_value = mock_llm_briefing_response

        result = generate_interview_briefing("EmptyTextCorp")

        assert "error" in result
        assert "Empty response from LLM" in result["error"]
        assert mock_llm_generate_content.call_count == 1

    @patch.object(llm_model_instance, 'generate_content')
    def test_json_cleaning_and_extraction_apify_off(self, mock_llm_generate_content, common_mocks_autouse):
        common_mocks_autouse.APIFY_API_KEY = None
        company_name = "CleaningTestCorp"
        expected_dict = {"key": "value"}
        raw_llm_text = f"```json\n{json.dumps(expected_dict)}\n```"

        mock_llm_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_response.text = raw_llm_text
        mock_llm_generate_content.return_value = mock_llm_response

        result = generate_interview_briefing(company_name)
        assert result == expected_dict
        mock_llm_generate_content.assert_called_once()

    # Logging tests can also be adapted by turning Apify off or by adding more specific checks
    # for logs related to Apify calls.
    @patch('backend.utils.llm_utils.logger')
    @patch.object(llm_model_instance, 'generate_content')
    def test_logging_on_success_apify_off(self, mock_llm_generate_content, mock_logger, common_mocks_autouse):
        common_mocks_autouse.APIFY_API_KEY = None
        company_name = "LoggingCorp"
        expected_briefing_dict = {"status": "success"}

        mock_llm_response = MagicMock(spec=GenerateTextResponse)
        mock_llm_response.text = json.dumps(expected_briefing_dict)
        mock_llm_generate_content.return_value = mock_llm_response

        generate_interview_briefing(company_name)

        mock_logger.info.assert_any_call(f"Calling generate_content for interview briefing for {company_name} (Attempt 1)")
        mock_logger.info.assert_any_call(f"Received response from model for {company_name}: {json.dumps(expected_briefing_dict)}")
        mock_logger.info.assert_any_call(f"Cleaned response for {company_name}: {json.dumps(expected_briefing_dict)}")
        # Check that Apify skip log appears
        mock_logger.warning.assert_any_call("APIFY_API_KEY not found. Apify related searches will be skipped.")
