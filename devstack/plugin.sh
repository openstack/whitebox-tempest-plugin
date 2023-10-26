#!/bin/sh

function configure {
    echo_summary "Configuring whitebox-tempest-plugin options"
    iniset $TEMPEST_CONFIG whitebox ctlplane_ssh_username $STACK_USER
    iniset $TEMPEST_CONFIG whitebox ctlplane_ssh_private_key_path $WHITEBOX_PRIVKEY_PATH

    # This needs to come from Zuul, as devstack itself has no idea how many
    # nodes are in the env
    iniset $TEMPEST_CONFIG whitebox max_compute_nodes $MAX_COMPUTE_NODES
    iniset $TEMPEST_CONFIG whitebox available_cinder_storage $WHITEBOX_AVAILABLE_CINDER_STORAGE
    if [ -n "$SMT_HOSTS" ]; then
        iniset $TEMPEST_CONFIG whitebox-hardware smt_hosts "$SMT_HOSTS"
    fi
    iniset $TEMPEST_CONFIG whitebox file_backed_memory_size $WHITEBOX_FILE_BACKED_MEMORY_SIZE
    iniset $TEMPEST_CONFIG whitebox cpu_model $WHITEBOX_CPU_MODEL
    iniset $TEMPEST_CONFIG whitebox cpu_model_extra_flags $WHITEBOX_CPU_MODEL_EXTRA_FLAGS
    iniset $TEMPEST_CONFIG whitebox rx_queue_size $WHITEBOX_RX_QUEUE_SIZE
    iniset $TEMPEST_CONFIG whitebox default_video_model $WHITEBOX_DEFAULT_VIDEO_MODEL
    iniset $TEMPEST_CONFIG whitebox max_disk_devices_to_attach $WHITEBOX_MAX_DISK_DEVICES_TO_ATTACH
    iniset $TEMPEST_CONFIG whitebox nodes_yaml $WHITEBOX_NODES_YAML

    iniset $TEMPEST_CONFIG whitebox-database user $DATABASE_USER
    iniset $TEMPEST_CONFIG whitebox-database password $DATABASE_PASSWORD
    iniset $TEMPEST_CONFIG whitebox-database host $DATABASE_HOST

    iniset $TEMPEST_CONFIG whitebox-hardware cpu_topology "$WHITEBOX_CPU_TOPOLOGY"
    iniset $TEMPEST_CONFIG whitebox-hardware dedicated_cpus_per_numa "$WHITEBOX_DEDICATED_CPUS_PER_NUMA"
    iniset $TEMPEST_CONFIG whitebox-hardware shared_cpus_per_numa "$WHITEBOX_SHARED_CPUS_PER_NUMA"

    iniset $TEMPEST_CONFIG compute-feature-enabled virtio_rng "$COMPUTE_FEATURE_VIRTIO_RNG"
    iniset $TEMPEST_CONFIG compute-feature-enabled rbd_download "$COMPUTE_FEATURE_RBD_DOWNLOAD"
    iniset $TEMPEST_CONFIG compute-feature-enabled uefi_secure_boot "$COMPUTE_FEATURE_UEFI_SECURE_BOOT"
    iniset $TEMPEST_CONFIG compute-feature-enabled bochs_display_support "$COMPUTE_FEATURE_BOCHS_DISPLAY"
    iniset $TEMPEST_CONFIG compute-feature-enabled vtpm_device_supported "$COMPUTE_FEATURE_VTPM_ENABLED"
    iniset $TEMPEST_CONFIG compute-feature-enabled live_migrate_back_and_forth "$COMPUTE_FEATURE_LIVE_MIGRATE_BACK_AND_FORTH"

    # matching devstack/lib/nova
    # https://github.com/openstack/devstack/blob/6b0f055b4ed407f8a190f768d0e654235ac015dd/lib/nova#L46C36-L46C50
    iniset $TEMPEST_CONFIG whitebox-nova-compute state_path $DATA_DIR/nova

}

if [[ "$1" == "stack" ]]; then
    if is_service_enabled tempest; then
        if [[ "$2" == "test-config" ]]; then
            configure
        fi
    fi
fi
