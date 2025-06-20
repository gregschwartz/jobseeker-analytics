import google.generativeai as genai
import time
import json
from google.ai.generativelanguage_v1beta2 import GenerateTextResponse
import logging
from apify_client import ApifyClient # Added ApifyClient import

from utils.config_utils import get_settings

settings = get_settings()

# Configure Google Gemini API
if settings.GOOGLE_API_KEY: # Check if API key exists
    genai.configure(api_key=settings.GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash-lite")
else:
    model = None # Or handle this case appropriately, e.g. by raising an error or using a mock model
    logging.warning("GOOGLE_API_KEY not found. LLM functionalities will be limited.")

logger = logging.getLogger(__name__)
# logging.basicConfig is typically called once. If called multiple times, it might not behave as expected.
# Assuming the first one is sufficient or this is handled at a higher application level.
# If not, this might need adjustment. For now, keeping as is from original.
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def process_email(email_text):
    prompt = f"""
        First, extract the job application status from the following email using the labels below. 
        If the status is 'False positive', only return the status as 'False positive' and do not extract company name or job title. 
        If the status is not 'False positive', then extract the company name and job title as well.
        
        Assign one of the following labels to job application status based on the main purpose or outcome of the message:
        
        Application confirmation
        Rejection
        Availability request
        Information request
        Assessment sent
        Interview invitation
        Did not apply - inbound request
        Action required from company
        Hiring freeze notification
        Withdrew application
        Offer made
        False positive

        Labeling Rules and Explanations for Job Application Status:

        Application confirmation
        Assign this label if the email confirms receipt of a job application.
        Examples: "We have received your application", "Thank you for applying", "Your application has been submitted".

        Rejection
        Use this label for emails explicitly stating that the candidate is not moving forward in the process.
        Examples: "We regret to inform you...", "We will not be proceeding with your application", "You have not been selected".

        Availability request
        Assign this label if the company asks for your availability for a call, interview, or meeting.
        Examples: "Please let us know your availability", "When are you free for a call?", "Can you share your available times?"

        Information request
        Use this label if the company requests additional information, documents, or clarification.
        Examples: "Please send your portfolio", "Can you provide references?", "We need more information about..."

        Assessment sent
        Assign this label if the company sends a test, assignment, or assessment for you to complete as part of the hiring process.
        Examples: "Please complete the attached assessment", "Here is your coding challenge", "Take-home assignment enclosed".

        Interview invitation
        Use this label if the company invites you to an interview (phone, video, or onsite).
        Examples: "We would like to invite you to interview", "Interview scheduled", "Please join us for an interview".

        Did not apply - inbound request
        Assign this label if the company or recruiter reaches out to you first about a job or recruiting opportunity, and you did not apply for the position.
        Examples: "We found your profile and would like to connect about a job", "Are you interested in this job opportunity?", "We came across your resume for a position".
        Do NOT use this label for event invitations, newsletters, or marketing emails.

        Action required from company
        Use this label if the next step is pending from the company, and you are waiting for their response or action.
        Examples: "We will get back to you", "Awaiting feedback from the team", "We will contact you with next steps".

        Hiring freeze notification
        Assign this label if the company notifies you that the position is on hold or canceled due to a hiring freeze.
        Examples: "Position is on hold", "Hiring freeze in effect", "We are pausing recruitment".

        Withdrew application
        Use this label if you (the candidate) have withdrawn your application, or the email confirms your withdrawal.
        Examples: "You have withdrawn your application", "Thank you for letting us know you are no longer interested".

        Offer made
        Assign this label if the company extends a job offer to you.
        Examples: "We are pleased to offer you the position", "Offer letter attached", "Congratulations, you have been selected".

        False positive
        Use this label if the email is not related to job applications, recruitment, or hiring.
        Examples: Newsletters, event invitations, conference invites, marketing emails, spam, unrelated notifications, or personal emails.
        Example: "Join us for our annual conference" → False positive
        Example: "Sign up for our upcoming event" → False positive

        If the status is 'False positive', only return: {{"job_application_status": "False positive"}}
        If the status is not 'False positive', return: {{"company_name": "company_name", "job_application_status": "status", "job_title": "job_title"}}
        Remove backticks. Only use double quotes. Enclose key and value pairs in a single pair of curly braces.
        Email: {email_text}
    """

    retries = 3  # Max retries
    delay = 60  # Initial delay
    for attempt in range(retries):
        try:
            logger.info("Calling generate_content")
            response: GenerateTextResponse = model.generate_content(prompt)
            response.resolve()
            response_json: str = response.text
            logger.info("Received response from model: %s", response_json)
            if response_json:
                cleaned_response_json = (
                    response_json.replace("json", "")
                    .replace("`", "")
                    .replace("'", '"')
                    .strip()
                )
                cleaned_response_json = (
                    response_json.replace("json", "")
                    .replace("`", "")
                    .replace("'", '"')
                    .strip()
                )
                logger.info("Cleaned response: %s", cleaned_response_json)
                return json.loads(cleaned_response_json)
            else:
                logger.error("Empty response received from the model.")
                return None
        except Exception as e:
            if "429" in str(e):
                logger.warning(
                    f"Rate limit hit. Retrying in {delay} seconds (attempt {attempt + 1})."
                )
                time.sleep(delay)
            else:
                logger.error(f"process_email exception: {e}")
                return None
    logger.error(f"Failed to process email after {retries} attempts.")
    return None


def generate_interview_briefing(company_name: str, interviewer_names: list[str] = None):
    if not model:
        logger.error("Google Gemini model not initialized due to missing API key.")
        return {"error": "LLM model not configured", "company_name": company_name}

    apify_client = None
    apify_company_data_summary_for_prompt = "(Simulated) Search for major news updates about the company in the last six months. Provide 2-3 example news headlines." # Default
    raw_apify_company_data = None # To store the direct output from Apify for company

    # Initialize Apify Client (same as before)
    if settings.APIFY_API_KEY:
        try:
            apify_client = ApifyClient(settings.APIFY_API_KEY)
        except Exception as e:
            logger.error(f"Failed to initialize ApifyClient: {e}")
            apify_client = None
    else:
        logger.warning("APIFY_API_KEY not found. Apify related searches will be skipped.")

    # 1. Attempt to get Company LinkedIn URL via LLM and then scrape with Apify
    if apify_client:
        company_linkedin_url = None
        try:
            # Prompt to find company LinkedIn URL
            url_search_prompt = f"""
                Based on the company name "{company_name}", what is the most likely official LinkedIn company page URL?
                Return only the URL. If unsure, return "NOT_FOUND".
                Example: https://www.linkedin.com/company/google
            """
            logger.info(f"Attempting to find LinkedIn URL for company: {company_name} using LLM.")
            url_response: GenerateTextResponse = model.generate_content(url_search_prompt)
            url_response.resolve()
            potential_url = url_response.text.strip()

            if "NOT_FOUND" not in potential_url and potential_url.startswith("http"):
                company_linkedin_url = potential_url
                logger.info(f"LLM suggested LinkedIn URL for {company_name}: {company_linkedin_url}")
            else:
                logger.warning(f"LLM could not confidently determine LinkedIn URL for {company_name}. Response: {potential_url}")
        except Exception as e:
            logger.error(f"Error during LLM call for company LinkedIn URL search for {company_name}: {e}")

        if company_linkedin_url:
            try:
                logger.info(f"Calling Apify actor for LinkedIn company data for URL: {company_linkedin_url}")
                # Using 'pocesar/linkedin-company-scraper' - verify this actor ID and its input structure.
                # This is a placeholder actor ID and might need to be changed.
                # Common input for such actors is a list of URLs: "start_urls": [{"url": company_linkedin_url}] or "linkedin_url": company_linkedin_url
                company_actor_input = {"linkedin_urls": [company_linkedin_url], "max_pages_to_scrape": 1} # Adjust input based on chosen actor

                # Placeholder actor ID - replace with a verified one.
                # For example, 'pocesar/linkedin-company-scraper' or 'gustavs/linkedin-company-scraper'
                # Let's use 'pocesar/linkedin-company-scraper' as a placeholder.
                company_actor_run = apify_client.actor("pocesar/linkedin-company-scraper").call(run_input=company_actor_input)

                logger.info(f"Apify company actor run initiated for {company_name}. Run ID: {company_actor_run.get('id', 'N/A')}, Dataset ID: {company_actor_run.get('defaultDatasetId', 'N/A')}")

                company_dataset_items = []
                for item in apify_client.dataset(company_actor_run["defaultDatasetId"]).iterate_items():
                    company_dataset_items.append(item)

                if company_dataset_items:
                    raw_apify_company_data = company_dataset_items[0]
                    logger.info(f"Received LinkedIn company data from Apify for {company_name}.")

                    # Construct company data summary for the main prompt
                    # Example fields: name, description, industry, companySize, headquarters, website
                    desc = raw_apify_company_data.get('description', '')
                    industry = raw_apify_company_data.get('industry', '')
                    size = raw_apify_company_data.get('companySize', '') # Or 'employees_count' etc.
                    hq = raw_apify_company_data.get('headquarters', {}).get('city', '') if raw_apify_company_data.get('headquarters') else '' # Path may vary
                    website = raw_apify_company_data.get('website', '') # Or 'company_website'

                    apify_company_data_summary_for_prompt = f"Retrieved LinkedIn Company Information for {company_name}:\n"
                    if desc: apify_company_data_summary_for_prompt += f"- About Us (from LinkedIn): {desc[:500]}...\n" # Truncate
                    if industry: apify_company_data_summary_for_prompt += f"- Industry: {industry}\n"
                    if size: apify_company_data_summary_for_prompt += f"- Company Size: {size}\n"
                    if hq: apify_company_data_summary_for_prompt += f"- Headquarters: {hq}\n"
                    if website: apify_company_data_summary_for_prompt += f"- Website: {website}\n"
                    apify_company_data_summary_for_prompt += "In addition to this, consider recent news (simulated search for 2-3 headlines) to generate company overview and talking points."
                else:
                    logger.warning(f"No data returned by Apify company actor for {company_name} at {company_linkedin_url}.")
                    # Fallback to default simulated news search if Apify company data fails
            except Exception as e:
                logger.error(f"Error during Apify company data call for {company_name}: {e}")
                # Fallback to default simulated news search
        else:
            logger.info(f"Skipping Apify company data fetch as no LinkedIn URL was obtained for {company_name}.")
            # Fallback to default simulated news search

    # 2. Interviewer processing (existing logic, slightly adapted for context)
    interviewer_prompt_sections = []
    if interviewer_names and apify_client: # Only try if names and client are available
        for interviewer_name in interviewer_names:
            # Default message if Apify fails or no data
            interviewer_specific_prompt = f"For Interviewer: {interviewer_name}\n(Simulated) Attempt to find their LinkedIn profile or general professional information. Provide a brief example summary of their role and experience. (Simulated) Generate 1-2 talking points."
            try:
                logger.info(f"Calling Apify actor for LinkedIn profile of '{interviewer_name}' at '{company_name}'.")
                run_input = {
                    "search_queries": [f"{interviewer_name} {company_name}"],
                    "max_items": 1,
                    "profile_scraper_mode": "full",
                }
                actor_run = apify_client.actor("harvestapi/linkedin-profile-search").call(run_input=run_input)
                logger.info(f"Apify actor run for '{interviewer_name}' initiated. Run ID: {actor_run.get('id', 'N/A')}")

                dataset_items = list(apify_client.dataset(actor_run["defaultDatasetId"]).iterate_items())
                if dataset_items:
                    profile_data = dataset_items[0]
                    logger.info(f"Received LinkedIn profile for '{interviewer_name}'.")

                    profile_url = profile_data.get('profile_url', 'N/A')
                    headline = profile_data.get('headline', '')
                    summary = profile_data.get('summary', '')
                    experience_list = profile_data.get('experience', [])
                    current_experience_str = ""
                    if experience_list:
                        current_experience_items = []
                        for exp in experience_list[:2]:
                            title = exp.get('title', 'N/A')
                            company = exp.get('company_name', 'N/A')
                            date_range = f"{exp.get('date_from', '')} - {exp.get('date_to', 'Present')}"
                            current_experience_items.append(f"{title} at {company} ({date_range})")
                        current_experience_str = "; ".join(current_experience_items)

                    interviewer_specific_prompt = f"For Interviewer: {interviewer_name}\nLinkedIn Profile Information (from {profile_url}):\n"
                    if headline: interviewer_specific_prompt += f"- Headline: {headline}\n"
                    if current_experience_str: interviewer_specific_prompt += f"- Current/Recent Role(s): {current_experience_str}\n"
                    if summary: interviewer_specific_prompt += f"- Summary Snippet: {summary[:300]}...\n"
                    interviewer_specific_prompt += "Based on this LinkedIn data, generate specific talking points."
                else:
                    logger.warning(f"No LinkedIn profile found by Apify for '{interviewer_name}'. Using simulation for prompt.")
            except Exception as e:
                logger.error(f"Error during Apify call for '{interviewer_name}': {e}. Using simulation for prompt.")

            interviewer_prompt_sections.append(interviewer_specific_prompt)
    elif interviewer_names: # Apify client not available, but names are
        for interviewer_name in interviewer_names:
            interviewer_prompt_sections.append(f"For Interviewer: {interviewer_name}\n(Simulated) Attempt to find their LinkedIn profile or general professional information. Provide a brief example summary of their role and experience. (Simulated) Generate 1-2 talking points as Apify client is not available.")

    final_interviewer_prompt_block = "\n\n".join(interviewer_prompt_sections) if interviewer_prompt_sections else "No interviewer names provided or Apify search skipped."


    # 3. Construct the main prompt for Gemini
    prompt = f"""
        Generate an interview briefing based on the provided company name, company data, and interviewer information.

        Company Name: {company_name}

        **Company Information Section:**
        {apify_company_data_summary_for_prompt}
        *   Based on the above information (LinkedIn data if provided, and simulated news), what does the company do?
        *   What is its mission and values (infer if not explicitly stated in provided data)?

        **Talking Points about the Company Section:**
        *   Generate 2-3 talking points about the company's purpose, recent developments, or its role in the industry, using the provided company information.

        **Interviewer Information Section:**
        {final_interviewer_prompt_block}
        *   For each interviewer, using the specific information provided (LinkedIn data or simulated), generate a brief professional summary and 1-2 targeted talking points. If no specific info was retrieved, state that and generate generic talking points based on their likely role.

        Output Format:
        Return the information as a structured JSON object. Example:
        {{
            "company_info": {{
                "description": "Example description of what the company does.",
                "mission": "Example mission statement.",
                "values": ["Example Value 1", "Example Value 2"],
                "recent_news": [ /* News headlines */ ]
            }},
            "company_talking_points": [ /* Company talking points */ ],
            "interviewers": [
                {{
                    "name": "Interviewer Name 1",
                    "info": "Generated summary of role, experience, possibly incorporating LinkedIn data if provided in prompt.",
                    "talking_points": [ /* Generated talking points for this interviewer */ ]
                }}
                // Add more interviewers if applicable
            ]
        }}

        If interviewer_names are not provided, the "interviewers" field in the JSON should be an empty list or omitted.
        If no information can be found for a specific interviewer (e.g. Apify error or no results), the 'info' should reflect that, and talking points should be generic or acknowledge lack of data.
        Ensure the output is a valid JSON. Do not include any text before or after the JSON object.
        Remove backticks. Only use double quotes.
    """

    retries = 3  # Max retries
    delay = 60  # Initial delay in seconds
        {{
            "company_info": {{
                "description": "Example description of what the company does.",
                "mission": "Example mission statement.",
                "values": ["Example Value 1", "Example Value 2"],
                "recent_news": [
                    "Example news headline 1 (Date)",
                    "Example news headline 2 (Date)"
                ]
            }},
            "company_talking_points": [
                "Example talking point 1 about company purpose/industry.",
                "Example talking point 2 about company purpose/industry."
            ],
            "interviewers": [
                {{
                    "name": "Interviewer Name 1",
                    "info": "Example: John Doe is a Senior Engineering Manager at {company_name} with 10 years of experience in cloud technologies. Previously worked at ExampleCorp.",
                    "talking_points": [
                        "Example talking point: Ask about their experience with cloud migration projects mentioned in their (simulated) profile.",
                        "Example talking point: Discuss their recent (simulated) article on AI ethics."
                    ]
                }}
            ]
        }}

        If interviewer_names are not provided, the "interviewers" field in the JSON should be an empty list or omitted.
        If no information can be found for a specific interviewer, provide a placeholder message in their "info" and "talking_points" fields.
        Ensure the output is a valid JSON. Do not include any text before or after the JSON object.
        Remove backticks. Only use double quotes.
    """

    retries = 3  # Max retries
    delay = 60  # Initial delay in seconds
    for attempt in range(retries):
        try:
            logger.info(
                f"Calling generate_content for interview briefing for {company_name} (Attempt {attempt + 1})"
            )
            response: GenerateTextResponse = model.generate_content(prompt)
            response.resolve() # Ensure the response is complete
            response_json_text = response.text
            logger.info(
                f"Received response from model for {company_name}: {response_json_text}"
            )

            if response_json_text:
                # Basic cleaning, similar to process_email. May need adjustment.
                cleaned_response_json = (
                    response_json_text.replace("json", "")
                    .replace("`", "")
                    .replace("'", '"')
                    .strip()
                )

                # Ensure it starts with { and ends with }
                if not cleaned_response_json.startswith("{") or not cleaned_response_json.endswith("}"):
                    # Attempt to extract JSON block if surrounded by other text
                    json_start = cleaned_response_json.find("{")
                    json_end = cleaned_response_json.rfind("}")
                    if json_start != -1 and json_end != -1 and json_start < json_end:
                        cleaned_response_json = cleaned_response_json[json_start : json_end + 1]
                    else:
                        logger.error(
                            f"Response for {company_name} is not a valid JSON structure: {cleaned_response_json}"
                        )
                        raise ValueError("Response is not a valid JSON structure after cleaning")


                logger.info(f"Cleaned response for {company_name}: {cleaned_response_json}")
                return json.loads(cleaned_response_json)
            else:
                logger.error(f"Empty response received from the model for {company_name}.")
                # No retry for empty response, as it's not a rate limit issue
                return {
                    "error": "Empty response from LLM",
                    "company_name": company_name,
                }

        except json.JSONDecodeError as e:
            logger.error(
                f"JSONDecodeError for {company_name} (Attempt {attempt + 1}): {e}. Response text: {response_json_text}"
            )
            if attempt < retries - 1:
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2 # Exponential backoff
            else:
                return {
                    "error": f"Failed to parse JSON response after {retries} attempts: {e}",
                    "company_name": company_name,
                    "raw_response": response_json_text,
                }
        except Exception as e:
            if "429" in str(e) or "Resource has been exhausted" in str(e): # Rate limit or quota
                logger.warning(
                    f"Rate limit/Quota hit for {company_name}. Retrying in {delay} seconds (attempt {attempt + 1}). Error: {e}"
                )
                time.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                logger.error(
                    f"generate_interview_briefing exception for {company_name} (Attempt {attempt + 1}): {e}"
                )
                # No retry for other general errors immediately
                return {
                    "error": f"An unexpected error occurred: {e}",
                    "company_name": company_name,
                }

    logger.error(
        f"Failed to generate interview briefing for {company_name} after {retries} attempts."
    )
    return {
        "error": f"Failed to generate interview briefing after {retries} attempts",
        "company_name": company_name,
    }
