import requests
import time
import json
import sys
import os
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("mitten_logs.txt"),
                        logging.StreamHandler()
                    ])

# Check if .env file exists
def check_env_file():
    if not os.path.exists('.env'):
        logging.error("'.env' file does not exist. Please create a .env file with the necessary environment variables to continue.\nExiting...")
        time.sleep(1)
        sys.exit(1)

# Get environment variables and handle missing or empty variables
def get_env_vars():
    load_dotenv()

    # Get environment variables
    REPOS = os.getenv('REPOS')
    DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL'))
    WEBHOOKS_ON_REPO_INIT = os.getenv('WEBHOOKS_ON_REPO_INIT')
    PREFER_AUTHOR_IN_TITLE = os.getenv('PREFER_AUTHOR_IN_TITLE')
    TEST_WEBHOOK_CONNECTION = os.getenv('TEST_WEBHOOK_CONNECTION')
    DISCORD_EMBED_COLOR = os.getenv('DISCORD_EMBED_COLOR')
    ROLES_TO_MENTION = os.getenv('ROLES_TO_MENTION')

    # Handle missing or empty environment variables
    if not REPOS:
        logging.error("'REPOS' environment variable is missing or empty. Please configure a list of repositories in your .env file to continue.\nExiting...")
        time.sleep(1)
        sys.exit(1)
    elif ',' in REPOS:
        REPOS = REPOS.split(',')
    else:
        REPOS = [REPOS]
    if not DISCORD_WEBHOOK_URL:
        logging.error("'DISCORD_WEBHOOK_URL' environment variable is missing or empty. Please configure a valid Discord webhook URL in your .env file to continue.\nExiting...")
        time.sleep(1)
        sys.exit(1)
    if not GITHUB_TOKEN:
        logging.warning("'GITHUB_TOKEN' environment variable is missing or empty. It is highly recommended to configure a GitHub API token to avoid rate limiting.\nLearn more: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens \n\nContinuing without a token in 10 seconds...\n")
        time.sleep(10)
    if not CHECK_INTERVAL:
        CHECK_INTERVAL = 60
        logging.warning("'CHECK_INTERVAL' environment variable is missing or empty. Defaulting to 60 seconds.")
        time.sleep(3)
    if not DISCORD_EMBED_COLOR:
        DISCORD_EMBED_COLOR = 0x222222
        logging.info("'DISCORD_EMBED_COLOR' environment variable is missing or empty. Defaulting to dark gray (Hex=0x222222).")
    if not ROLES_TO_MENTION:
        ROLES_TO_MENTION = ""
        logging.info("'ROLES_TO_MENTION' environment variable is missing or empty. No roles will be mentioned in notifications.")
    if not WEBHOOKS_ON_REPO_INIT:
        WEBHOOKS_ON_REPO_INIT = True
        logging.info("'WEBHOOKS_ON_REPO_INIT' environment variable is missing or empty. Defaulting to True.")
    if not PREFER_AUTHOR_IN_TITLE:
        PREFER_AUTHOR_IN_TITLE = False
        logging.info("'PREFER_AUTHOR_IN_TITLE' environment variable is missing or empty. Defaulting to False.")
    if TEST_WEBHOOK_CONNECTION == 'True':
        send_test_webhook_message(DISCORD_WEBHOOK_URL, ROLES_TO_MENTION)

    return REPOS, DISCORD_WEBHOOK_URL, GITHUB_TOKEN, CHECK_INTERVAL, DISCORD_EMBED_COLOR, ROLES_TO_MENTION, WEBHOOKS_ON_REPO_INIT, PREFER_AUTHOR_IN_TITLE

# Headers for authenticated requests
def construct_headers(GITHUB_TOKEN):
    headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}

    return headers

# Determine the rate limit value based on the presence of a GitHub token
def determine_rate_limit(GITHUB_TOKEN):
    rate_limit = '5000' if GITHUB_TOKEN else '60'

    return rate_limit

# Parse repositories and branches
def parse_repos(REPOS, headers):
    parsed_repos = []
    commit_log = load_commit_log()

    for repo in REPOS:
        if ':' in repo:
            repo_name, branch = repo.split(':')
        else:
            repo_name = repo
            branch = None
            # Find the branch from the commit log
            for key in commit_log:
                if key.startswith(repo_name + ':'):
                    branch = key.split(':')[1]
                    break
            if not branch:
                branch = get_default_branch(repo_name, headers)
            logging.info(f"Branch not specified for repository: {repo_name}. Defaulting to branch: {branch}")

        # Update the parsed_repos list with the repo and branch
        parsed_repos.append((repo_name, branch))

    return parsed_repos

# Parse the Link header to extract the next page URL
def parse_link_header(link_header):
    links = {}
    parts = link_header.split(',')
    for part in parts:
        section = part.split(';')
        if len(section) < 2:
            continue
        url = section[0].strip('<>')
        rel = section[1].strip().split('=')[1].strip('"')
        links[rel] = url

    return links

# Load existing log data
def load_commit_log():
    if os.path.exists('commit_log.json'):
        with open('commit_log.json', 'r') as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                return {}
    else:
        return {}

# Save log data
def save_commit_log(commit_log):
    with open('commit_log.json', 'w') as file:
        json.dump(commit_log, file, indent=4)

# Check if a commit has been logged
def has_been_logged(key, commit_sha, commit_log):
    return commit_log.get(key, {}).get(commit_sha, False)

# Log a notified commit
def log_notified_commit(key, commit_sha, commit_log):
    if key not in commit_log:
        commit_log[key] = {}
    commit_log[key][commit_sha] = True
    save_commit_log(commit_log)

# Get the default branch for a repository
def get_default_branch(repo, headers):
    url = f'https://api.github.com/repos/{repo}'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    repo_info = response.json()

    return repo_info['default_branch']

# Function to format the API rate limit reset time into a human-readable string
def format_reset_time(rate_limit_reset_time):
    remaining_time = rate_limit_reset_time - time.time()
    remaining_minutes = int((remaining_time % 3600) / 60)
    remaining_seconds = int(remaining_time % 60)
    if 10 < remaining_minutes < 60:
        return f"{remaining_minutes} minute(s)"
    elif 1 < remaining_minutes < 10:
        return f"{remaining_minutes} minute(s), and {remaining_seconds % 60} second(s)"
    else:
        return f"{remaining_seconds} second(s)"

# Monitor GitHub API usage
def monitor_api_usage(headers):
    url = 'https://api.github.com/rate_limit'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    requests_remaining = response.json()['rate']['remaining']
    rate_limit_reset_time = response.json()['rate']['reset']

    return requests_remaining, rate_limit_reset_time

# Fetch commits of a repository since the last known commit
def fetch_new_commits(repo, branch, PREFER_AUTHOR_IN_TITLE, headers, last_seen_timestamp=None):
    # Construct the URL to fetch commits
    url = f'https://api.github.com/repos/{repo}/commits?sha={branch}'

    if PREFER_AUTHOR_IN_TITLE == 'True':
        # Fetch commits
        if last_seen_timestamp:
            url += f'&since={last_seen_timestamp}'
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        commits = response.json()

        # Add the commit author name and their GitHub avatar URL to each commit
        for commit in commits:
            if commit.get('author'):
                committer_name = commit['author']['login']
                committer_avatar_url = commit['author']['avatar_url']
            else:
                committer_name = 'Unknown'
                committer_avatar_url = ''

            commit['title_name'] = committer_name
            commit['title_image'] = committer_avatar_url

    else:
        # Fetch general repository information
        repo_info_url = f'https://api.github.com/repos/{repo}'
        repo_info_response = requests.get(repo_info_url, headers=headers)
        repo_info_response.raise_for_status()
        repo_info = repo_info_response.json()

        # Extract name and avatar_url from the repo owner
        repo_name = repo_info['name']
        owner_avatar_url = repo_info['owner']['avatar_url']

        # Fetch commits
        if last_seen_timestamp:
            url += f'&since={last_seen_timestamp}'
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        commits = response.json()

        # Add the repo name and its owner's GitHub avatar URL to each commit
        for commit in commits:
            commit['title_name'] = repo_name
            commit['title_image'] = owner_avatar_url

    return commits

# Fetch all commits of a repository
def fetch_all_commits(repo, branch, GITHUB_TOKEN, headers):
    # Construct the URL to fetch commits
    url = f'https://api.github.com/repos/{repo}/commits?sha={branch}'

    # Fetch commits in batches
    commits = []
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code == 403:
            reset_time = int(response.headers['X-RateLimit-Reset'])
            wait_time = reset_time - time.time()
            logging.warning(f"Rate limit exceeded. Waiting for {int(wait_time)} second(s).")
            if not GITHUB_TOKEN:
                logging.info("It is highly recommended to configure a GitHub API token to avoid rate limiting.\nLearn more: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens")
            while wait_time > 0:
                logging.info(f"Waiting for {int(wait_time)} second(s)...")
                time.sleep(5)
                wait_time -= 5
            continue
        response.raise_for_status()
        batch = response.json()
        commits.extend(batch)
        link_header = response.headers.get('Link')
        if link_header:
            links = parse_link_header(link_header)
            next_link = links.get('next')
            if next_link:
                url = next_link
            else:
                url = None
        else:
            url = None

    return commits

# Initialize each new repository with its entire commit history to avoid spamming notifications
def initialize_repo_log(repo, branch, DISCORD_WEBHOOK_URL, GITHUB_TOKEN, CHECK_INTERVAL, WEBHOOKS_ON_REPO_INIT, commit_log, latest_commits, new_repos, headers, initial_message_sent=False):
    key = f"{repo}:{branch}"
    key_tuple = (repo, branch)
    repo_index = new_repos.index(key_tuple) + 1  # Track the index of the current repository being initialized

    # Notify and log the start of repo initialization
    logging.info(f"({repo_index}/{len(new_repos)}) Initializing log for new repository: {key} (This may take a while if it's a large repository...)")
    if WEBHOOKS_ON_REPO_INIT == True:
        notify_discord_repo_init(repo, branch, DISCORD_WEBHOOK_URL, repo_index, new_repos, headers, commits=0, is_start=True, initial_message_sent=False)

    # Fetch all existing commits of the repository
    requests_remaining, rate_limit_reset_time = monitor_api_usage(headers)
    commits = fetch_all_commits(repo, branch, GITHUB_TOKEN, headers)

    # Save the commit log and update the latest commit timestamp for the repo/branch
    if key not in commit_log:
        commit_log[key] = {}
    for commit in commits:
        commit_sha = commit['sha']
        commit_log[key][commit_sha] = True
    save_commit_log(commit_log)

    # Update the latest commit timestamp for the repo/branch
    if commits:
        latest_commits[key] = commits[0]['commit']['committer']['date']
    logging.info(f"({repo_index}/{len(new_repos)}) Initialized {len(commits)} commits from the {branch} branch of repository: {repo}")
    logging.info(f"({repo_index}/{len(new_repos)}) API requests remaining after initialization: {requests_remaining}")

    # Notify and log the completion of repo initialization
    if WEBHOOKS_ON_REPO_INIT == True:
        notify_discord_repo_init(repo, branch, DISCORD_WEBHOOK_URL, repo_index, new_repos, headers, commits, is_start=False, initial_message_sent=True)
    if repo_index == len(new_repos):
        logging.info(f"Done! Successfully initialized {len(new_repos)} repositories. Checking for new commits every {CHECK_INTERVAL} seconds...")

def send_test_webhook_message(DISCORD_WEBHOOK_URL, ROLES_TO_MENTION):
    role_mentions = "".join(f"<@&{role_id}>" if role_id.isdigit() else role_id for role_id in ROLES_TO_MENTION.split(','))
    if "@everyone" in ROLES_TO_MENTION.split(','):
        role_mentions += " @everyone"

    test_message = {
        "content": role_mentions,
        "embeds": [
            {
                "title": "Success",
                "description": "This is a test message from Mitten v1.2.",
                "thumbnail": {
                    "url": "https://static-00.iconduck.com/assets.00/success-icon-512x512-qdg1isa0.png"
                },
                "color": 0x21c179,
            }
        ]
    }
    response = requests.post(DISCORD_WEBHOOK_URL, json=test_message)

    if response.status_code == 204:
        logging.info("Test message sent successfully.")
    else:
        logging.error(f"Failed to send test message to Discord. Status code: {response.status_code}\nExiting...")
        time.sleep(1)
        sys.exit(1)

# Send a notification to Discord about the initialization of a new repository or the completion of initialization.
def notify_discord_repo_init(repo, branch, DISCORD_WEBHOOK_URL, repo_index, new_repos, headers, commits, is_start=True, initial_message_sent=False):
    key = f"{repo}:{branch}"
    repo_name = repo.split('/')[1]

    # Construct and send the initial message if it is the first repository being initialized
    if repo_index == 1 and not initial_message_sent:
        formatted_new_repos = '\n'.join([f"- {repo[0].replace(', ', ':').replace('(', '').replace(')', '').replace('[', '').replace(']', '')}:{repo[1]}" for repo in new_repos])
        initial_message = f"**{len(new_repos)}** new repositories detected: \n{formatted_new_repos}"
        initial_description = f"Initializing commit logs for **{len(new_repos)}** new repositories..."

        initial_embed = {
            "embeds": [
                {
                    "author": {
                        "name": "Initializing New Repositories",
                    },
                    "title": initial_message,
                    "description": initial_description,
                    "thumbnail": {
                        "url": "https://icons.veryicon.com/png/o/education-technology/library-icon/system-log-2.png"
                    },
                    "fields": [
                        {
                            "name": "Notice",
                            "value": "Mitten saves a local copy of each repository's commit history to avoid spam and duplicate notifications. This only needs to be done once for each repository in your list."
                        }
                    ]
                }
            ]
        }
        # Send the initial Discord embed
        response = requests.post(DISCORD_WEBHOOK_URL, json=initial_embed)
        response.raise_for_status()
        initial_message_sent = True
        time.sleep(1)  # Avoid Discord webhook rate limiting

    # Construct the message and description based on whether the initialization is starting or ending
    if is_start:
        message = f"**({repo_index}/{len(new_repos)})** Initializing log for new repository: {key}"
        description = "This may take a while for large repositories..."
    else:
        message = f"**({repo_index}/{len(new_repos)})** Done initializing repository: {key}"
        description = f"Initialized all **{len(commits)}** commits from `{branch}` branch of {repo}.\n\nReady to receive notifications for new commits."

    # Construct the URL to fetch repository info
    repo_info_url = f'https://api.github.com/repos/{repo}'

    # Construct the Discord embed
    discord_embed = {
        "embeds": [
            {
                "author": {
                    "name": repo_name,
                    "icon_url": requests.get(repo_info_url, headers=headers).json()['owner']['avatar_url'],
                },
                "title": message,
                "description": description,
            }
        ]
    }
    # Send the Discord embed for each new repository initialization
    response = requests.post(DISCORD_WEBHOOK_URL, json=discord_embed)
    response.raise_for_status()
    time.sleep(1)  # Avoid Discord webhook rate limiting

# Send a notification to Discord about the new commit
def notify_discord(repo, branch, commit, DISCORD_WEBHOOK_URL, DISCORD_EMBED_COLOR, ROLES_TO_MENTION, headers):
    key = f"{repo}:{branch}"
    commit_sha = commit['sha']
    commit_message = commit['commit']['message']
    commit_log = load_commit_log()

    role_mentions = " ".join(f"<@&{role_id}>" for role_id in ROLES_TO_MENTION.split(',') if role_id.isdigit())
    if "@everyone" in ROLES_TO_MENTION.split(','):
        role_mentions += " @everyone"

    # Extract and split the commit message and description
    if '\n\n' in commit_message:
        simple_commit_message, commit_description = commit_message.split('\n\n', 1)
    elif '\n' in commit_message:
        simple_commit_message, commit_description = commit_message.split('\n', 1)
    else:
        simple_commit_message = commit_message
        commit_description = 'No description provided'

    # Extract relevant commit information
    commit_url = commit['html_url']
    pushed_at = commit['commit']['committer']['date']
    title_image = commit['title_image']
    repo_url = f"https://github.com/{repo}"

    # Log the notified commit
    log_notified_commit(key, commit_sha, commit_log)

    # Construct the Discord embed
    discord_embed = {
        "content": ROLES_TO_MENTION,
        "embeds": [
            {
                "author": {
                    "name": commit['title_name'],
                    "icon_url": title_image
                },
                "title": f"New commit in {repo}",
                "url": repo_url,
                "timestamp": pushed_at,
                "color": int(DISCORD_EMBED_COLOR, 16),
                "fields": [
                    {
                        "name": "Commit",
                        "value": f"[`{commit_sha[:7]}`]({commit_url}) {simple_commit_message}"
                    }
                ]
            }
        ]
    }
    # Check if commit description is provided and is not the default placeholder
    if commit_description != "No description provided":
        description_field = {
            "name": "Description",
            "value": commit_description
        }
        discord_embed["embeds"][0]["fields"].append(description_field)

    # Check if the commit is not on the default branch or if the repo appears more than once in the REPOS environment variable
    default_branch = get_default_branch(repo, headers)  # Retrieve the default branch name
    repos_env = os.getenv('REPOS', '')  # Re-fetch the REPOS environment variable, default to empty if not set

    # Clean repo names by removing everything after the colon and then count occurrences
    cleaned_repos = [repo.split(':')[0] for repo in repos_env.split(',')]
    repo_count = cleaned_repos.count(repo.split(':')[0])  # Count occurrences of the current repo in the cleaned list

    # Add a 'Branch' field to the embed if the commit is not on the default branch or if the repo appears more than once in the REPOS environment variable
    if branch != default_branch or repo_count > 1:
        branch_field = {
            "name": "Branch",
            "value": f"`{branch}`"
        }
        discord_embed["embeds"][0]["fields"].append(branch_field)

    # Split the commit description into lines for formatting in the log message
    description_lines = commit_description.splitlines()

    # Construct the log message
    log_message = (f"Sending message to Discord for new commit in {branch} branch of {repo}\n"
                f"                                     Commit SHA: {commit_sha}\n"
                f"                                     Commit Message: {simple_commit_message}\n"
                f"                                     Description: {description_lines[0]}\n")
    for line in description_lines[1:]:
        log_message += f"                                                  {line}\n"
    log_message += f"                                     Commit URL: {commit_url}"

    # Log the message
    logging.info(log_message)

    # Send the Discord embed for each new commit
    response = requests.post(DISCORD_WEBHOOK_URL, json=discord_embed)
    response.raise_for_status()
    time.sleep(1)  # Avoid Discord webhook rate limiting

# Check each repository for new commits
def check_repo(repo, branch, latest_commits, DISCORD_WEBHOOK_URL, DISCORD_EMBED_COLOR, ROLES_TO_MENTION, PREFER_AUTHOR_IN_TITLE, rate_limit, headers):
    try:
        key = f"{repo}:{branch}"
        last_seen_timestamp = latest_commits.get(key)
        new_commits = fetch_new_commits(repo, branch, PREFER_AUTHOR_IN_TITLE, headers, last_seen_timestamp)
        if new_commits:
            # Sort commits by timestamp to ensure correct order
            new_commits.sort(key=lambda commit: commit['commit']['committer']['date'])
            # Update the latest commit timestamp for the repo to the most recent commit
            latest_commit_timestamp = new_commits[-1]['commit']['committer']['date']
            latest_commits[key] = latest_commit_timestamp

            # Notify for each new commit if it has not been logged
            for commit in new_commits:
                commit_sha = commit['sha']
                commit_log = load_commit_log()
                if has_been_logged(key, commit_sha, commit_log):  # Check if already notified/logged
                    logging.info(f"Commit #{commit_sha} in {repo} on {branch} branch has already been logged. Watching for new commits...")
                    return
                else:  # Notify for each new commit
                    notify_discord(repo, branch, commit, DISCORD_WEBHOOK_URL, DISCORD_EMBED_COLOR, ROLES_TO_MENTION, headers)

    # Handle exceptions and log errors
    except requests.RequestException as e:
        requests_remaining, rate_limit_reset_time = monitor_api_usage(headers)
        formatted_reset_time = format_reset_time(rate_limit_reset_time)
        logging.error(f"Error fetching commits for {repo}: {e}")
        logging.warning(f"API requests remaining: {requests_remaining} | Rate limit resets to '{rate_limit}' in {formatted_reset_time}")

# Main function to begin monitoring repositories for new commits
def main():
    logging.info("Starting Mitten (v1.2)")

    # Check for the existence of the .env file
    check_env_file()

    # Get and handle errors for environment variables
    REPOS, DISCORD_WEBHOOK_URL, GITHUB_TOKEN, CHECK_INTERVAL, DISCORD_EMBED_COLOR, ROLES_TO_MENTION, WEBHOOKS_ON_REPO_INIT, PREFER_AUTHOR_IN_TITLE = get_env_vars()

    # Construct headers for authenticated requests
    headers = construct_headers(GITHUB_TOKEN)

    # Determine the rate limit value based on the presence of a GitHub token
    rate_limit = determine_rate_limit(GITHUB_TOKEN)

    # Parse repositories and branches
    parsed_repos = parse_repos(REPOS, headers)

    formatted_repos = '\n                                 '.join([f"• {repo[0].replace(', ', ':').replace('(', '').replace(')', '').replace('[', '').replace(']', '')}:{repo[1]}" for repo in parsed_repos])
    logging.info(f"Monitoring {len(parsed_repos)} repositories: \n                                 {formatted_repos}")
    commit_log = load_commit_log()

    # Stores the timestamp of the latest commit seen for each repo
    latest_commits = {}

    # Check for new repositories not found in the commit_log.json
    new_repos = [r for r in parsed_repos if f"{r[0]}:{r[1]}" not in commit_log.keys()]
    formatted_new_repos = '\n                                 '.join([f"• {repo[0].replace(', ', ':').replace('(', '').replace(')', '').replace('[', '').replace(']', '')}:{repo[1]}" for repo in new_repos])
    if new_repos:
        logging.info(f"{len(new_repos)} new repositories detected: \n                                 {formatted_new_repos}")
        logging.info("[Notice] Mitten saves a local copy of each repository's commit history to avoid spam and duplicate notifications. This may take a while for large repositories, but only needs to be done once for each repository in your list.")
        logging.info(f"Initializing commit logs for {len(new_repos)} new repositories...")
        for repo, branch in new_repos:
            initialize_repo_log(repo, branch, DISCORD_WEBHOOK_URL, GITHUB_TOKEN, CHECK_INTERVAL, WEBHOOKS_ON_REPO_INIT, commit_log, latest_commits, new_repos, headers)
    else:
        logging.info(f"No new repositories detected. Checking for new commits every {CHECK_INTERVAL} seconds...")

    # Main loop to check for new commits
    while True:
        requests_remaining, rate_limit_reset_time = monitor_api_usage(headers)
        formatted_reset_time = format_reset_time(rate_limit_reset_time)
        if requests_remaining < (10 * len(parsed_repos)):  # Adjust the polling interval to mitigate rate limiting
            logging.warning(f"API rate limit is low ({requests_remaining} requests remaining). Adjusting polling interval and waiting for {CHECK_INTERVAL * 2} seconds.")
            if not GITHUB_TOKEN:
                logging.warning("It is highly recommended to configure a GitHub API token to avoid rate limiting.\nLearn more: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens")
            time.sleep(CHECK_INTERVAL * 2)
            continue

        # Log each new scan, as well as the current API requests remaining and rate limit reset time
        logging.info(f"Starting new scan... | API requests remaining: {requests_remaining} | Rate limit resets to '{rate_limit}' in {formatted_reset_time}")

        # Check each repository for new commits
        for repo, branch in parsed_repos:
            try:
                check_repo(repo, branch, latest_commits, DISCORD_WEBHOOK_URL, DISCORD_EMBED_COLOR, ROLES_TO_MENTION, PREFER_AUTHOR_IN_TITLE, rate_limit, headers)
            except Exception as e:
                logging.error(f"Error occurred while checking repository {repo}: {e}")

        # Log the end of each scan
        logging.info(f"Scan completed. Waiting for {CHECK_INTERVAL} seconds...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
