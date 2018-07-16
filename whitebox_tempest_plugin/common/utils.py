# Copyright 2017 Red Hat
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

from oslo_log import log as logging
from tempest import config


CONF = config.CONF
LOG = logging.getLogger(__name__)


def get_hypervisor_ip(admin_servers_client, server_id):
    server = admin_servers_client.show_server(server_id)
    host = server['server']['OS-EXT-SRV-ATTR:host']
    try:
        return CONF.whitebox.hypervisors[host]
    except KeyError:
        LOG.error('Unable to find IP in conf. Server: %s, host: %s.',
                  (server_id, host))
