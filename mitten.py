import requests
import time
import json
import sys
import os
import logging
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("mitten_logs.txt"),
                        logging.StreamHandler()
                    ])

# Check if .env file exists
if not os.path.exists('.env'):
    logging.error("'.env' file does not exist. Please create a .env file with the necessary environment variables to continue.\nExiting...")
    time.sleep(1)
    sys.exit(1)

# Load environment variables from .env file
load_dotenv()

# Get environment variables and handle missing or empty variables
repos = os.getenv('REPOS')
if repos is None:
    logging.error("'REPOS' environment variable is missing or empty. Please configure a list of repositories in your .env file to continue.\nExiting...")
    time.sleep(1)
    sys.exit(1)
elif ',' in repos:
    repos = repos.split(',')
else:
    repos = [repos]

discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
if not discord_webhook_url:
    logging.error("'DISCORD_WEBHOOK_URL' environment variable is missing or empty. Please configure a valid Discord webhook URL in your .env file to continue.\nExiting...")
    time.sleep(1)
    sys.exit(1)

github_token = os.getenv('GITHUB_TOKEN')
if not github_token:
    logging.warning("'GITHUB_TOKEN' environment variable is missing or empty. It is highly recommended to configure a GitHub API token to avoid rate limiting.\nLearn more: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens \n\nContinuing without a token in 10 seconds...\n")
    time.sleep(10)

interval = int(os.getenv('CHECK_INTERVAL'))
if not interval:
    interval = 60
    logging.warning("'CHECK_INTERVAL' environment variable is missing or empty. Defaulting to 60 seconds.")
    time.sleep(3)

# Headers for authenticated requests
headers = {'Authorization': f'token {github_token}'} if github_token else {}

# Stores the timestamp of the latest commit seen for each repo
latest_commits = {}

# Determine the rate limit value based on the presence of a GitHub token
rate_limit = '5000' if github_token else '60'

# Fetch all commits of a repository
def fetch_all_commits(repo):
    url = f'https://api.github.com/repos/{repo}/commits'
    commits = []
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code == 403:
            reset_time = int(response.headers['X-RateLimit-Reset'])
            wait_time = reset_time - time.time()
            logging.warning(f"Rate limit exceeded. Waiting for {int(wait_time)} second(s).")
            if not github_token:
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

# Fetch commits of a repository since the last known commit
def fetch_repo_info(repo, last_seen_timestamp=None):
    # Fetch general repository information
    repo_info_url = f'https://api.github.com/repos/{repo}'
    repo_info_response = requests.get(repo_info_url, headers=headers)
    repo_info_response.raise_for_status()
    repo_info = repo_info_response.json()

    # Fetch commits
    url = f'https://api.github.com/repos/{repo}/commits'
    if last_seen_timestamp:
        url += f'?since={last_seen_timestamp}'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    commits = response.json()

    # Extract name and avatar_url from owner
    repo_name = repo_info['name']
    owner_avatar_url = repo_info['owner']['avatar_url']

    # Add name and avatar_url to each commit
    for commit in commits:
        commit['repo_name'] = repo_name
        commit['owner_avatar_url'] = owner_avatar_url

    return commits

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
def has_been_logged(repo, commit_sha, commit_log):
    return commit_log.get(repo, {}).get(commit_sha, False)

# Log a notified commit
def log_notified_commit(repo, commit_sha, commit_log):
    if repo not in commit_log:
        commit_log[repo] = {}
    commit_log[repo][commit_sha] = True
    save_commit_log(commit_log)

# Initialize each new repository with its entire commit history to avoid spamming notifications
def initialize_repo_log(repo, commit_log, new_repos):
    repo_index = new_repos.index(repo) + 1
    logging.info(f"({repo_index}/{len(new_repos)}) Initializing log for new repository: {repo} (This may take a while if it's a large repository...)")
    requests_remaining, rate_limit_reset_time = monitor_api_usage()
    commits = fetch_all_commits(repo)
    if repo not in commit_log:
        commit_log[repo] = {}
    for commit in commits:
        commit_sha = commit['sha']
        commit_log[repo][commit_sha] = True
    save_commit_log(commit_log)
    if commits:
        latest_commits[repo] = commits[0]['commit']['committer']['date']
    logging.info(f"({repo_index}/{len(new_repos)}) Initialized {len(commits)} commits for repository: {repo}")
    logging.info(f"({repo_index}/{len(new_repos)}) API requests remaining after initialization of {repo}: {requests_remaining}")
    if repo_index == len(new_repos):
        logging.info(f"Done! Successfully initialized {len(new_repos)} repositories. Checking for new commits every {interval} seconds...")

# Send a notification to Discord about the new commit
def notify_discord(repo, commit):
    commit_sha = commit['sha']
    commit_message = commit['commit']['message']
    commit_log = load_commit_log()

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
    owner_avatar_url = commit['owner_avatar_url']
    repo_url = f"https://github.com/{repo}"

    # Log the notified commit
    log_notified_commit(repo, commit_sha, commit_log)

    # Construct the Discord embed
    if commit_description == 'No description provided':
        discord_embed = {
            "embeds": [
                {
                    "author": {
                        "name": commit['repo_name'],
                        "icon_url": owner_avatar_url
                    },
                    "title": f"New commit in {repo}",
                    "url": repo_url,
                    "timestamp": pushed_at,
                    "fields": [
                        {
                            "name": "Commit",
                            "value": f"[`{commit_sha[:7]}`]({commit_url}) {simple_commit_message}"
                        }
                    ]
                }
            ]
        }
    else:
        discord_embed = {
            "embeds": [
                {
                    "author": {
                        "name": commit['repo_name'],
                        "icon_url": owner_avatar_url
                    },
                    "title": f"New commit in {repo}",
                    "url": repo_url,
                    "timestamp": pushed_at,
                    "fields": [
                        {
                            "name": "Commit",
                            "value": f"[`{commit_sha[:7]}`]({commit_url}) {simple_commit_message}"
                        },
                        {
                            "name": "Description",
                            "value": commit_description
                        }
                    ]
                }
            ]
        }

    # Split the commit description into lines for formatting in the log message
    description_lines = commit_description.splitlines()

    # Construct the log message
    log_message = (f"Sending message to Discord for new commit in {repo}\n"
                f"                                     Commit SHA: {commit_sha}\n"
                f"                                     Commit Message: {simple_commit_message}\n"
                f"                                     Description: {description_lines[0]}\n")
    for line in description_lines[1:]:
        log_message += f"                                                  {line}\n"
    log_message += f"                                     Commit URL: {commit_url}"

    # Log the message
    logging.info(log_message)

    # Send the Discord embed
    response = requests.post(discord_webhook_url, json=discord_embed)
    response.raise_for_status()
    time.sleep(1)  # Avoid Discord webhook rate limiting

# Check each repository for new commits
def check_repo(repo):
    try:
        last_seen_timestamp = latest_commits.get(repo)
        new_commits = fetch_repo_info(repo, last_seen_timestamp)
        if new_commits:
            # Sort commits by timestamp to ensure correct order
            new_commits.sort(key=lambda commit: commit['commit']['committer']['date'])
            # Update the latest commit timestamp for the repo to the most recent commit
            latest_commit_timestamp = new_commits[-1]['commit']['committer']['date']
            latest_commits[repo] = latest_commit_timestamp

            # Notify for each new commit if it has not been logged
            for commit in new_commits:
                commit_sha = commit['sha']
                commit_log = load_commit_log()
                if has_been_logged(repo, commit_sha, commit_log):  # Check if already notified/logged
                    logging.info(f"Commit #{commit_sha} in {repo} has already been logged. Watching for new commits...")
                    return
                else:  # Notify for each new commit
                    notify_discord(repo, commit)

    except requests.RequestException as e:
        requests_remaining, rate_limit_reset_time = monitor_api_usage()
        formatted_reset_time = format_reset_time(rate_limit_reset_time)
        logging.error(f"Error fetching commits for {repo}: {e}")
        # Log the current API requests remaining and rate limit reset time
        logging.warning(f"API requests remaining: {requests_remaining} | Rate limit resets to '{rate_limit}' in {formatted_reset_time}")

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
def monitor_api_usage():
    url = 'https://api.github.com/rate_limit'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    requests_remaining = response.json()['rate']['remaining']
    rate_limit_reset_time = response.json()['rate']['reset']

    return requests_remaining, rate_limit_reset_time

# Main function to orchestrate the checking and notification process
def main():
    # Enable multi-threading to check multiple repositories concurrently (Set this to 'False' if you are having issues with notifications or rate limiting)
    enable_multi_threading = False

    logging.info("Starting Mitten (v1.1.6)")
    logging.info(f"Monitoring {len(repos)} repositories: {repos}")
    commit_log = load_commit_log()

    # Check for new repositories not found in the commit_log.json
    new_repos = [r for r in repos if r not in commit_log]
    if new_repos:
        logging.info(f"{len(new_repos)} new repositories detected: {new_repos}")
        logging.info("Notice: Mitten saves a local copy of each repository's commit history to avoid spam and duplicate notifications. This may take a while for large repositories, but only needs to be done once for each repository in your list.")
        logging.info(f"Initializing commit logs for {len(new_repos)} new repositories...")
        for repo in new_repos:
            initialize_repo_log(repo, commit_log, new_repos)
    else:
        logging.info(f"No new repositories detected. Checking for new commits every {interval} seconds...")

    while True:
        requests_remaining, rate_limit_reset_time = monitor_api_usage()
        formatted_reset_time = format_reset_time(rate_limit_reset_time)
        if requests_remaining < (10 * len(repos)):  # Adjust the polling interval to avoid rate limiting
            logging.warning(f"API rate limit is low ({requests_remaining} requests remaining). Adjusting polling interval and waiting for {interval * 2} seconds.")
            if not github_token:
                logging.warning("It is highly recommended to configure a GitHub API token to avoid rate limiting.\nLearn more: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens")
            time.sleep(interval * 2)
            continue

        # Log each new scan, as well as the current API requests remaining and rate limit reset time
        logging.info(f"Starting new scan... | API requests remaining: {requests_remaining} | Rate limit resets to '{rate_limit}' in {formatted_reset_time}")

        # Enable multi-threading to check multiple repositories concurrently
        if enable_multi_threading:
            with ThreadPoolExecutor() as executor:
                futures = [executor.submit(check_repo, repo) for repo in repos]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logging.error(f"Error occurred while checking repository: {e}")
        else:
            for repo in repos:
                try:
                    check_repo(repo)
                except Exception as e:
                    logging.error(f"Error occurred while checking repository: {e}")

        # Log the end of each scan
        logging.info(f"Scan completed. Waiting for {interval} seconds...")
        time.sleep(interval)

if __name__ == "__main__":
    main()
