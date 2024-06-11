import requests
import time
import json
import os
import logging
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables from a .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Discord webhook URL from environment variables
discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL')

# Stores the timestamp of the latest commit seen for each repo
latest_commits = {}

# Fetch all commits of a repository
def fetch_all_commits(repo):
    url = f'https://api.github.com/repos/{repo}/commits'
    commits = []
    while url:
        response = requests.get(url)
        response.raise_for_status()
        batch = response.json()
        commits.extend(batch)
        url = response.links.get('next', {}).get('url')
    return commits

# Fetch commits of a repository since the last known commit
def fetch_repo_info(repo, last_seen_timestamp=None):
    url = f'https://api.github.com/repos/{repo}/commits'
    if last_seen_timestamp:
        url += f'?since={last_seen_timestamp}'
    response = requests.get(url)
    response.raise_for_status()
    commits = response.json()

    # Fetch repository information
    repo_info_url = f'https://api.github.com/repos/{repo}'
    repo_info_response = requests.get(repo_info_url)
    repo_info_response.raise_for_status()
    repo_info = repo_info_response.json()

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

# Check if a commit has been notified
def has_been_notified(repo, commit_sha, commit_log):
    return commit_log.get(repo, {}).get(commit_sha, False)

# Log a notified commit
def log_notified_commit(repo, commit_sha, commit_log):
    if repo not in commit_log:
        commit_log[repo] = {}
    commit_log[repo][commit_sha] = True
    save_commit_log(commit_log)

# Initialize any new repository with all of its commits to avoid spamming notifications
def initialize_repo_log(repo, commit_log):
    logging.info(f"Initializing log for new repository: {repo}")
    commits = fetch_all_commits(repo)
    if repo not in commit_log:
        commit_log[repo] = {}
    for commit in commits:
        commit_sha = commit['sha']
        commit_log[repo][commit_sha] = True
    save_commit_log(commit_log)
    if commits:
        latest_commits[repo] = commits[0]['commit']['committer']['date']
    logging.info(f"Initialized {len(commits)} commits for repository: {repo}")

# Send a notification to Discord about the new commit
def notify_discord(repo, commit):
    commit_sha = commit['sha']
    commit_message = commit['commit']['message']
    commit_log = load_commit_log()

    # Check if already notified
    if has_been_notified(repo, commit_sha, commit_log):
        logging.info(f"Commit #{commit_sha} in {repo} has already been logged. Watching for new commits...")
        return

    if '\n\n' in commit_message:
        simple_commit_message, commit_description = commit_message.split('\n\n', 1)
    elif '\n' in commit_message:
        simple_commit_message, commit_description = commit_message.split('\n', 1)
    else:
        simple_commit_message = commit_message
        commit_description = 'No description provided'

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

    logging.info(f"Sending message to Discord for new commit in {repo}:\n"
                 f"    Commit SHA: {commit_sha}\n"
                 f"    Commit Message: {simple_commit_message}\n"
                 f"    Description: {commit_description[:50]}...\n"
                 f"    Commit URL: {commit_url}")

    response = requests.post(discord_webhook_url, json=discord_embed)
    response.raise_for_status()

# Check each repository for new commits
def check_repo(repo):
    try:
        commit_log = load_commit_log()
        if repo not in commit_log:
            initialize_repo_log(repo, commit_log)
            logging.info(f"Skipping initial fetch for {repo} following initialization")
            return  # Failsafe to avoid spam notifications, temporarily skip fetching new commits right after initialization
        last_seen_timestamp = latest_commits.get(repo)
        new_commits = fetch_repo_info(repo, last_seen_timestamp)
        if new_commits:
            # Sort commits by timestamp to ensure correct order
            new_commits.sort(key=lambda commit: commit['commit']['committer']['date'])
            # Update the latest commit timestamp for the repo to the most recent commit
            latest_commit_timestamp = new_commits[-1]['commit']['committer']['date']
            latest_commits[repo] = latest_commit_timestamp
            # Notify for each new commit
            for commit in new_commits:
                notify_discord(repo, commit)
    except requests.RequestException as e:
        logging.error(f"Error fetching commits for {repo}: {e}")

# Main function to orchestrate the checking and notification process
def main():
    repos = os.getenv('REPOS').split(',')
    interval = int(os.getenv('CHECK_INTERVAL'))
    while True:
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(check_repo, repo) for repo in repos]
            for future in as_completed(futures):
                future.result()
        time.sleep(interval)

if __name__ == "__main__":
    main()
