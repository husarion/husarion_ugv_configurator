# husarion_ugv_configurator

## Installation

Simply run:

```bash
just install
```

## Running Husarion UGV Configurator TUI

```bash
just husarion_ugv_configurator
```

## Using standalone `just` commands

Suggested way of using the configurator is with the `husarion_ugv_configurator` application. This section describes some of the available `just` that are used by the application, but can be also used as a standalone commands.

You can list all available commands with:

```bash
just --list
```

### Initializing configuration

To initialize the configuration, run (you will be asked for password, default: husarion):

```bash
just init_config
```

### Modifying configuration

Edit files inside the `config` directory, then apply changes to the driver.

```bash
just update_config
just restart_driver
```

### Restore default configuration

This command will overwrite all files in the `config` directory to their default state for the currently running driver version.

```bash
just restore_default
```

To completely erase all changes made to the `config` directory (except for files located in `config/common`), use the restore command with `hard` mode:

```bash
just restore_default hard
```

::Warning::
> This will completely erase all data from the `config` directory except for files located in the `config/common` subdirectory.

### Update driver version

List available stable driver versions:

```bash
just list_driver_versions
# To list for a specific ROS distro
just list_driver_versions humble
```

Choose the newest tag and update the driver:

```bash
just update_driver_version <tag>
# Example
just update_driver_version humble-2.1.2-20241125
```

### Debug driver

Logs from the driver can be seen using following command:

```bash
just driver_logs
```

To follow the output.

```bash
just driver_logs -f
```
