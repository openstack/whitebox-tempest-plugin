# Copyright 2021 Red Hat Inc.
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

from tempest import config

from whitebox_tempest_plugin.services.key_manager.json import base


CONF = config.CONF


class SecretClient(base.BarbicanTempestClient):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._secret_ids = set()

    def get_secret(self, secret_id):
        resp, body = self.get("v1/secrets/%s" % secret_id)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_secrets(self, **kwargs):
        uri = "v1/secrets"
        if kwargs is not None:
            uri = '{base}?'.format(base=uri)

            for key in kwargs.keys():
                uri = '{base}&{name}={value}'.format(
                    base=uri,
                    name=key,
                    value=kwargs[key]
                )
        resp, body = self.get(uri)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)
