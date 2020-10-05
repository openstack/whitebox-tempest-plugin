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


def parse_cpu_spec(spec):
    """Parse a CPU set specification.

    NOTE(artom): This has been lifted from Nova with minor
    exceptions-related adjustments.

    Each element in the list is either a single CPU number, a range of
    CPU numbers, or a caret followed by a CPU number to be excluded
    from a previous range.

    :param spec: cpu set string eg "1-4,^3,6"

    :returns: a set of CPU indexes
    """
    cpuset_ids = set()
    cpuset_reject_ids = set()
    for rule in spec.split(','):
        rule = rule.strip()
        # Handle multi ','
        if len(rule) < 1:
            continue
        # Note the count limit in the .split() call
        range_parts = rule.split('-', 1)
        if len(range_parts) > 1:
            reject = False
            if range_parts[0] and range_parts[0][0] == '^':
                reject = True
                range_parts[0] = str(range_parts[0][1:])

            # So, this was a range; start by converting the parts to ints
            try:
                start, end = [int(p.strip()) for p in range_parts]
            except ValueError:
                raise exceptions.InvalidCPUSpec(spec=spec)
            # Make sure it's a valid range
            if start > end:
                raise exceptions.InvalidCPUSpec(spec=spec)
            # Add available CPU ids to set
            if not reject:
                cpuset_ids |= set(range(start, end + 1))
            else:
                cpuset_reject_ids |= set(range(start, end + 1))
        elif rule[0] == '^':
            # Not a range, the rule is an exclusion rule; convert to int
            try:
                cpuset_reject_ids.add(int(rule[1:].strip()))
            except ValueError:
                raise exceptions.InvalidCPUSpec(spec=spec)
        else:
            # OK, a single CPU to include; convert to int
            try:
                cpuset_ids.add(int(rule))
            except ValueError:
                raise exceptions.InvalidCPUSpec(spec=spec)

    # Use sets to handle the exclusion rules for us
    cpuset_ids -= cpuset_reject_ids

    return cpuset_ids
