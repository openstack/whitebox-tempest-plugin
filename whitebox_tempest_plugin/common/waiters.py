# Copyright 2020
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import time

from tempest.lib import exceptions as lib_exc
from whitebox_tempest_plugin.exceptions import MigrationException


def wait_for_nova_service_state(client, host, binary, status_field, state):
    timeout = client.build_timeout
    start_time = int(time.time())
    # NOTE(artom) Assumes that the (host, binary) combination will yield a
    # unique service. There is no service in Nova that can run multiple copies
    # on the same host.
    service = client.list_services(host=host, binary=binary)['services'][0]
    while service[status_field] != state:
        time.sleep(client.build_interval)
        timed_out = int(time.time()) - start_time >= timeout
        if timed_out:
            raise lib_exc.TimeoutException(
                'Service %s on host %s failed to reach state %s within '
                'the required time (%s s)', binary, host, state, timeout)
        service = client.list_services(host=host, binary=binary)['services'][0]


def wait_for_server_migration_complete(os_admin, server_id):
    start_time = int(time.time())
    timeout = os_admin.services_client.build_timeout
    interval = os_admin.services_client.build_interval + 1
    while int(time.time()) - start_time <= timeout:
        s_migs = os_admin.migrations_client.list_migrations()
        if s_migs['migrations'][-1]['status'] in ['done', 'completed']:
            break
        elif s_migs['migrations'][-1]['status'] in ['error', 'failed']:
            raise MigrationException(
                'Evacuation failed, because server migration failed.')
        time.sleep(interval)
    else:
        # raise Timeout exception if migration never completed
        raise lib_exc.TimeoutException(
            'Evacuation failed, because server migration did not '
            'complete, within the required time: (%s s)' % timeout)
