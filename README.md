<h1 align="center">
  Mitten
</h1>

<p align="center">
  <img width="180" height="180" src="https://i.imgur.com/ptCgBYk.png">
</p>

**Mitten** is a Python script designed to monitor GitHub repositories for new commits and send notifications to a specified Discord channel. The script leverages the GitHub API to fetch commit information and Discord Webhooks to post notifications.

## Features

- Fetches commits from specified GitHub repositories.
- Sends commit notifications to Discord with detailed commit information.
- Supports multiple repositories concurrently using threading. (Toggleable in the script's main function, turn this off if you are having issues with notifications or rate limiting.)
- Logs commit information locally to avoid duplicate notifications.
- Fetches commits pushed since the last runtime of the script, ensuring that commits pushed during downtime are still fetched in the next run.
- Configurable through environment variables.

## Requirements

- Python 3.7+
- `requests` library
- `python-dotenv` library

## Configuration
Create a '**.env**' file in the same directory as the script with the following variables:
- **REPOS**: A comma-separated list of repositories to monitor. (e.g., '**user/repo1,user/repo2**').
- **DISCORD_WEBHOOK_URL**: The Discord webhook URL where notifications will be sent.
- **GITHUB_TOKEN**: (Optional but **highly recommended**) Your GitHub API token to avoid rate limiting. Learn more about creating a personal access token [here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
- **CHECK_INTERVAL**: The interval (in seconds) at which the script checks for new commits. 

### Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/joobert/mitten.git
    cd mitten
    ```

2. Install dependencies:
    ```sh
    pip install -r requirements.txt
    ```

3. Create a `.env` file with the following content:
    ```env
    REPOS=owner/repo1,owner/repo2,owner/repo3
    DISCORD_WEBHOOK_URL=your_webhook_url
    GITHUB_TOKEN=your_github_token
    CHECK_INTERVAL=60
    ```

4. Run the script:
    ```sh
    python mitten.py
    ```

### (Optional) Running with Docker

###### Ensure you have both Docker and Docker Compose installed on your machine.

1. Clone the repository:
    ```sh
    git clone https://github.com/joobert/mitten.git
    cd mitten
    ```

2. Create a `.env` file with the following content:
    ```env
    REPOS=owner/repo1,owner/repo2,owner/repo3
    DISCORD_WEBHOOK_URL=your_webhook_url
    GITHUB_TOKEN=your_github_token
    CHECK_INTERVAL=60
    ```

3. Create an empty `commit_log.json` file:
    ```sh
    touch commit_log.json
    ```

4. Start the service with Docker Compose:
    ```sh
    docker-compose up -d
    ```

## Important Notes

- **Initial Run**: On the first run (and for each subsequent repository added down the line), Mitten will initialize each repository by fetching its entire commit history to avoid spamming notifications and fetch commits pushed during the script's downtime on the next run. This process can be API heavy and time-consuming for large repositories, but only needs to be done once per repository.

- **GitHub Token**: It is highly recommended to set a GitHub API token to avoid API rate limiting issues. Without the token, you will be limited to 60 requests per hour, which might not be sufficient for monitoring multiple repositories, nor sufficient for the initial run of a large repository. Setting the token increases this limit significantly (5000 requests per hour) ensuring you won't run into issues.

- **Logging**: Mitten creates and logs commit information locally in a file named '**commit_log.json**' to ensure that no duplicate notifications are sent. The script also saves its runtime logs to a file named '**mitten_logs.txt**'. Both of these should be kept in the same directory as the script.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an Issue.

## License

[MIT](https://choosealicense.com/licenses/mit/)
