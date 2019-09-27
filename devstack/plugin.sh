#!/bin/sh

function install {
    echo_summary "Installing whitebox-tempest-plugin"
    setup_dev_lib "whitebox-tempest-plugin"
}

function configure {
    echo_summary "Configuring whitebox-tempest-plugin options"
    iniset $TEMPEST_CONFIG whitebox ctlplane_ssh_username $STACK_USER
    iniset $TEMPEST_CONFIG whitebox ctlplane_ssh_private_key_path $WHITEBOX_PRIVKEY_PATH

    # This needs to come from Zuul, as devstack itself has no idea how many
    # nodes are in the env
    iniset $TEMPEST_CONFIG whitebox max_compute_nodes $MAX_COMPUTE_NODES

    iniset $TEMPEST_CONFIG whitebox-nova-compute config_path "$WHITEBOX_NOVA_COMPUTE_CONFIG_PATH"
    iniset $TEMPEST_CONFIG whitebox-nova-compute restart_command "$WHITEBOX_NOVA_COMPUTE_RESTART_COMMAND"

    iniset $TEMPEST_CONFIG whitebox-database user $DATABASE_USER
    iniset $TEMPEST_CONFIG whitebox-database password $DATABASE_PASSWORD
    iniset $TEMPEST_CONFIG whitebox-database host $DATABASE_HOST
}

if [[ "$1" == "stack" ]]; then
    if is_service_enabled tempest; then
        if [[ "$2" == "install" ]]; then
            install
        elif [[ "$2" == "test-config" ]]; then
            configure
        fi
    fi
fi
