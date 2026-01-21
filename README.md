# Spacebot

**CAUTION: This repository has been migrated to codeberg, and now lives at [codeberg.org/technikkultur-erfurt/spacebot](https://codeberg.org/technikkultur-erfurt/spacebot).**
**This repository is now an archive.**

---

matrix-nio based bot using plugins to realize commands and auto announcements.

## Plugins
| Plugin | Description |
| --- | --- |
| amtsblatt | Link to "Amtsblatt der Landeshauptstadt Erfurt" and announce new releases |
| dates | Next dates from configured icals and announce upcoming events |
| echo | Print text after keyword |
| mowas | Alert messsages from Modulares Warnsystem |
| now | Current date and time |
| rss | Latest entries from RSS feeds and announce new entries |
| status | Current room status |

## Dependencies
### System (Debian-related)
* git
* python3 (>=3.8, tested with 3.11)
* python3-venv

### Python modules
* see [requirements.txt](requirements.txt)

## Installation

You should install this application using a dedicated user.

### System requirements on Debian

1. Install system requirements
    ```shell
    sudo apt-get update
    sudo apt-get install python3-venv git
    ```

2. Create spacebot user
    ```shell
    sudo useradd --comment "Spacebot" --create-home  --user-group spacebot
    ```

### Spacebot

1. Change to spacebot user
    ```shell
    sudo su - spacebot
    ```

2. Clone repository
    ```shell
    git clone https://github.com/Bytespeicher/spacebot
    ```
3. Initialize virtual environment
    ```shell
    python3 -m venv virtualenv3
    ```
4. Install python requirements in virtual environment
    ```shell
    . virtualenv3/bin/activate
    pip3 install -r spacebot/requirements.txt
    deactivate
    ```
5. Copy example configuration files
    ```shell
    cd ~/spacebot
    cp config/config.example.yaml config/config.yaml
    ```

6. Adjust configuration file config/config.yaml

### Install systemd unit

1. Copy systemd unit file
    ```shell
    sudo cp /home/spacebot/spacebot/contrib/spacebot.service /etc/systemd/system/spacebot.service
    ```

3. Reload systemd daemon to reload unit file and start and enable service
    ```shell
    sudo systemctl daemon-reload
    sudo systemctl enable spacebot.service --now
    ```
## Update

### Spacebot

1. Change to spacebot user
    ```shell
    sudo su - spacebot
    ```

2. Update repository
    ```shell
    cd spacebot
    git pull
    ```

3. Update virtual environment
    ```shell
    cd
    python3 -m venv --upgrade virtualenv3
    ```

4. Update python requirements in virtual environment
    ```shell
    cd
    . virtualenv3/bin/activate
    pip3 install --upgrade -r spacebot/requirements.txt
    deactivate
    ```

5. Adjust configuration file config/config.yaml

6. Restart systemd daemon
    ```shell
    sudo systemctl restart spacebot.service
    ```
