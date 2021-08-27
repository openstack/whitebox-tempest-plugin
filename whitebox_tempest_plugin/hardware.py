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

from tempest import config
from whitebox_tempest_plugin import exceptions


CONF = config.CONF


def get_all_cpus():
    """Aggregate the dictionary values of [whitebox]/cpu_topology from
    tempest.conf into a list of pCPU ids.
    """
    topology_dict = CONF.whitebox_hardware.cpu_topology
    cpus = []
    [cpus.extend(c) for c in topology_dict.values()]
    return cpus


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


def format_cpu_spec(cpu_list):
    """Returns a libvirt-style CPU spec from the provided list of integers. For
    example, given [0, 2, 3], returns "0,2,3".
    """
    return ','.join(map(str, cpu_list))


def get_pci_address(domain, bus, slot, func):
    """Assembles PCI address components into a fully-specified PCI address.

    NOTE(jparker): This has been lifted from nova.pci.utils with no
    adjustments

    Does not validate that the components are valid hex or wildcard values.
    :param domain, bus, slot, func: Hex or wildcard strings.
    :return: A string of the form "<domain>:<bus>:<slot>.<function>".
    """
    return '%s:%s:%s.%s' % (domain, bus, slot, func)
