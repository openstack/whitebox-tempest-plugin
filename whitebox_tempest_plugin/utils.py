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

if six.PY2:
    import contextlib2 as contextlib
else:
    import contextlib


def normalize_json(json):
    """Normalizes a JSON dict for consistent equality tests. Sorts the keys,
    and sorts any values that are lists.
    """
    def sort_list_values(json):
        for k, v in json.items():
            if isinstance(v, list):
                v.sort()
            elif isinstance(v, dict):
                sort_list_values(v)

    json = jsonutils.loads(jsonutils.dumps(json, sort_keys=True))
    sort_list_values(json)
    return json


@contextlib.contextmanager
def multicontext(*context_managers):
    with contextlib.ExitStack() as stack:
        yield [stack.enter_context(mgr) for mgr in context_managers]
