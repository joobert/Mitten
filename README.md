<h1 align="center">
  Mitten
</h1>

<p align="center">
  <img width="180" height="180" src="https://i.imgur.com/ptCgBYk.png">
</p>

Mitten is a Python script designed to monitor GitHub repositories for new commits and send notifications to a specified Discord channel. The script leverages the GitHub API to fetch commit information and Discord Webhooks to post notifications.

## Features

- Fetches commits from specified GitHub repositories.
- Sends commit notifications to Discord with detailed commit information.
- Supports multiple repositories concurrently using threading.
- Logs notified commits to avoid duplicate notifications.
- Fetches commits pushed since the last runtime of the script, ensuring that commits pushed during downtime are still fetched in the next run.
- Configurable through environment variables.

## Requirements

- Python 3.7+
- `requests` library
- `python-dotenv` library

### Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/joobert/mitten.git
    cd Mitten
    ```

2. Install dependencies:
    ```sh
    pip install -r requirements.txt
    ```

3. Create a `.env` file with the following content:
    ```env
    DISCORD_WEBHOOK_URL=your_webhook_url
    REPOS=owner/repo1,owner/repo2,owner/repo3
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
    cd Mitten
    ```

2. Create a `.env` file with the following content:
    ```env
    DISCORD_WEBHOOK_URL=your_webhook_url
    REPOS=owner/repo1,owner/repo2,owner/repo3
    CHECK_INTERVAL=60
    ```

3. Start the service with Docker Compose:
    ```sh
    docker-compose up -d
    ```

## Configuration

- **DISCORD_WEBHOOK_URL**: Your Discord webhook URL.
- **REPOS**: Comma-separated list of repositories to monitor.
- **CHECK_INTERVAL**: Interval in seconds between checks.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an Issue.

## License

[MIT](https://choosealicense.com/licenses/mit/)
