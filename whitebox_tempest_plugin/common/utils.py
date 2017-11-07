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


def _get_hv_ip_from_conf(id):
    conf_hvs = CONF.whitebox.hypervisors
    if conf_hvs:
        return conf_hvs.get(id)


def get_hypervisor_ip(client, hostname):
    """Finds the IP address of a compute node based on its hostname. This is
    necessary in case a compute node isn't accessible by its IP address as it
    appears in the nova API. Such a situation arises in infrared deployments of
    OSP12, for example.

    :param client: The hypervisors client to use.
    :param hostname: The compute node's hostname, from the instance's
                     OS-EXT-SRV-ATTR:host attribute.
    :return: The IP address of the compute node - either as configuired in the
             hypervisors section of our config file, or as returned by the nova
             API as fallback.
     """
    hvs = client.list_hypervisors(detail=True)['hypervisors']
    compute_node_address = None
    for hv in hvs:
        if hv['service']['host'] == hostname:
            hv_ip = _get_hv_ip_from_conf(str(hv['id']))
            if hv_ip:
                compute_node_address = hv_ip
                LOG.info('Using %s for hypervisor %s '
                         'from config file', (hv_ip, hv['id']))
            else:
                compute_node_address = hv['host_ip']
                LOG.info('Using %s as fallback since hypervisor %s not '
                         'in config file', (compute_node_address,
                                            hv['id']))
    return compute_node_address
