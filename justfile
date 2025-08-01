remote_ip := "10.15.20.2"
remote_host := "husarion"

[private]
default:
    @just --list --unsorted

_install_package package:
  #!/bin/bash
  if ! command -v {{package}} &> /dev/null; then
    echo "Installing {{package}}"
    sudo apt update && sudo apt install -y {{package}}
  else
    echo "{{package}} is already installed"
  fi

_ssh_command +command:
  ssh -o ConnectTimeout=10 -n {{remote_host}}@{{remote_ip}} "{{command}}"

_install_dependencies:
  @echo "Installing dependencies"
  just _install_package rsync

init_config: _install_dependencies
  @echo "Initializing config directory..."
  mkdir -p config
  ssh-copy-id -o ConnectTimeout=10 {{remote_host}}@{{remote_ip}}
  rsync -e 'ssh -o ConnectTimeout=10' -avr {{remote_host}}@{{remote_ip}}:/home/husarion/config/ ./config/

update_config:
  @echo "Updating robot configuration..."
  rsync -e 'ssh -o ConnectTimeout=10' -avr ./config/ {{remote_host}}@{{remote_ip}}:/home/husarion/config/

restart_driver:
  @echo "Restarting driver..."
  just _ssh_command "bash -l -c 'docker compose up --force-recreate -d' >/dev/null 2>&1"
  @echo "Driver restarted successfully."

driver_logs *additional_args:
  @echo "Starting driver logs..."
  just _ssh_command "docker logs husarion_ugv_ros {{additional_args}}"

restore_default mode="soft":
  @echo "Restoring default robot configuration..."
  {{ if mode == "hard" { "just _hard_reset" } else { "" } }}
  just _ssh_command "docker exec husarion_ugv_ros bash -c 'source /ros2_ws/install/setup.bash && update_config_directory'"
  just init_config

_hard_reset:
  @echo "Performing hard reset"
  find ./config -mindepth 1 -maxdepth 1 -not -name 'common' -exec rm -rf {} +
  just _ssh_command "find /home/husarion/config -mindepth 1 -maxdepth 1 -not -name 'common' -exec rm -rf {} +"

list_driver_versions ros_distro="humble":
  @echo "Listing available driver versions"
  wget -q -O - "https://hub.docker.com/v2/namespaces/husarion/repositories/husarion-ugv/tags?page_size=100" | \
  grep -o '"name": *"[^"]*' | \
  grep -o '[^"]*$' | \
  grep "{{ros_distro}}-[0-9]*\.[0-9]*\.[0-9]-[0-9]\{8\}$" | \
  sort -V

update_driver_version version:
  #!/bin/bash
  ros_distro=$(echo "{{version}}" | cut -d'-' -f1)
  if ! just list_driver_versions $ros_distro | grep -qw "^{{version}}$"; then
    echo "Version {{version}} not found"
    exit 1
  fi
  echo "Updating driver to version {{version}}"
  just _ssh_command "sed -i 's/\(image: husarion\/husarion-ugv:\)[^ ]*/\1{{version}}/' /home/husarion/compose.yaml" || exit

  echo "You should restart the driver to apply changes."

robot_info:
  #!/bin/bash
  info=$(just _ssh_command "bash -c -l 'printenv ROBOT_MODEL ROBOT_MODEL_NAME ROBOT_SERIAL_NO ROBOT_VERSION SYSTEM_BUILD_VERSION >&3' 3>&1 1>/dev/null 2>&1")
  driver_version=$(just _ssh_command "docker inspect --format='{{'{{.Config.Image}}'}}' husarion_ugv_ros")
  echo "$info" | {
    read -r model
    read -r model_name
    read -r serial_no
    read -r version
    read -r system_version
    echo "ROBOT_MODEL=$model"
    echo "ROBOT_MODEL_NAME=$model_name"
    echo "ROBOT_SERIAL_NO=$serial_no"
    echo "ROBOT_VERSION=$version"
    echo "SYSTEM_BUILD_VERSION=$system_version"
    echo "DRIVER_VERSION=$driver_version"
  }

install: init_config
  #!/bin/bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip3 install -r requirements.txt
  deactivate

husarion_ugv_configurator:
  COLORTERM=truecolor ./configurator.py
