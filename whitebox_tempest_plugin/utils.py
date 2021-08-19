# Copyright 2020 Red Hat
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

import six

from oslo_serialization import jsonutils
from tempest import config
from whitebox_tempest_plugin import exceptions

if six.PY2:
    import contextlib2 as contextlib
else:
    import contextlib

CONF = config.CONF


def normalize_json(json):
    """Normalizes a JSON dict for consistent equality tests. Sorts the keys,
    and sorts any values that are lists.
    """
    def sort_list_values(json):
        for k, v in json.items():
            if isinstance(v, list):
                v.sort()
                [sort_list_values(x) for x in v if isinstance(x, dict)]
            elif isinstance(v, dict):
                sort_list_values(v)

    json = jsonutils.loads(jsonutils.dumps(json, sort_keys=True))
    sort_list_values(json)
    return json


@contextlib.contextmanager
def multicontext(*context_managers):
    with contextlib.ExitStack() as stack:
        yield [stack.enter_context(mgr) for mgr in context_managers]


def get_ctlplane_address(compute_hostname):
    """Return the appropriate host address depending on a deployment.

    In TripleO deployments the Undercloud does not have DNS entries for
    the compute hosts. This method checks if there are 'DNS' mappings of
    the provided hostname to its control plane IP address and returns it.
    For Devstack deployments, no such parameters will exist and the method
    will just return compute_hostname

    :param compute_hostname: str the compute hostname
    :return: The address to be used to access the compute host. For
    devstack deployments, this is compute_host itself. For TripleO, it needs
    to be looked up in the configuration.
    """
    if not CONF.whitebox.ctlplane_addresses:
        return compute_hostname

    if compute_hostname in CONF.whitebox.ctlplane_addresses:
        return CONF.whitebox.ctlplane_addresses[compute_hostname]

    raise exceptions.CtrlplaneAddressResolutionError(host=compute_hostname)
