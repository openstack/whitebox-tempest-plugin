# Copyright 2018 Red Hat
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

from tempest.lib import exceptions


class CtrlplaneAddressResolutionError(exceptions.TempestException):
    message = "Unable to find address in conf. Host: %(host)s."


class MissingServiceSectionException(exceptions.TempestException):
    message = "Unable to find whitebox-%(service)s section in configuration."


class InvalidCPUSpec(exceptions.TempestException):
    message = "CPU spec is invalid: %(spec)s."


class MigrationException(exceptions.TempestException):
    message = "Migration Failed: %(msg)s."
