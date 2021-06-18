#
# MIT License
#
# Copyright (c) 2020 Airbyte
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#


from typing import Any, List, Mapping, Tuple

from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http.auth import TokenAuthenticator

from .streams import (
    Branches,
    Commits,
    EpicIssues,
    Epics,
    GitlabStream,
    Groups,
    Issues,
    Jobs,
    Labels,
    Members,
    MergeRequestCommits,
    MergeRequests,
    Milestones,
    Pipelines,
    PipelinesExtended,
    Projects,
    Releases,
    Tags,
    Users,
)


class SourceGitlab(AbstractSource):
    def _generate_main_streams(self, config: Mapping[str, Any]) -> Tuple[GitlabStream, GitlabStream]:
        gids = list(filter(None, config["groups"].split(" ")))
        pids = list(filter(None, config["projects"].split(" ")))

        if not pids and not gids:
            raise Exception("Either groups or projects need to be provided for connect to Gitlab API")

        auth = TokenAuthenticator(token=config["private_token"])
        auth_params = dict(authenticator=auth, api_url=config["api_url"])
        groups = Groups(group_ids=gids, **auth_params)
        if gids:
            projects = Projects(project_ids=pids, parent_stream=groups, **auth_params)
        else:
            projects = Projects(project_ids=pids, **auth_params)

        return groups, projects

    def check_connection(self, logger, config) -> Tuple[bool, any]:
        try:
            groups, projects = self._generate_main_streams(config)
            for stream in projects.stream_slices(sync_mode=SyncMode.full_refresh):
                list(projects.read_records(sync_mode=SyncMode.full_refresh, stream_slice=stream))
            return True, None
        except Exception as error:
            return False, f"Unable to connect to Gitlab API with the provided credentials - {repr(error)}"

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        auth = TokenAuthenticator(token=config["private_token"])
        auth_params = dict(authenticator=auth, api_url=config["api_url"])

        groups, projects = self._generate_main_streams(config)
        pipelines = Pipelines(parent_stream=projects, start_date=config["start_date"], **auth_params)
        merge_requests = MergeRequests(parent_stream=projects, start_date=config["start_date"], **auth_params)

        streams = [
            groups,
            projects,
            Branches(parent_stream=projects, repository_part=True, **auth_params),
            Commits(parent_stream=projects, repository_part=True, start_date=config["start_date"], **auth_params),
            Issues(parent_stream=projects, start_date=config["start_date"], **auth_params),
            Jobs(parent_stream=pipelines, **auth_params),
            Milestones(parent_stream=projects, parent_similar=True, **auth_params),
            Milestones(parent_stream=groups, parent_similar=True, **auth_params),
            Members(parent_stream=projects, parent_similar=True, **auth_params),
            Members(parent_stream=groups, parent_similar=True, **auth_params),
            Labels(parent_stream=projects, parent_similar=True, **auth_params),
            Labels(parent_stream=groups, parent_similar=True, **auth_params),
            merge_requests,
            Releases(parent_stream=projects, **auth_params),
            Tags(parent_stream=projects, repository_part=True, **auth_params),
            pipelines,
            Users(parent_stream=projects, **auth_params),
        ]

        # Enabling additional streams according to the setting
        if config["ultimate_license"]:
            epics = Epics(parent_stream=groups, **auth_params)
            streams += [epics, EpicIssues(parent_stream=epics, **auth_params)]

        if config["fetch_merge_request_commits"]:
            streams.append(MergeRequestCommits(parent_stream=merge_requests, **auth_params))

        if config["fetch_pipelines_extended"]:
            streams.append(PipelinesExtended(parent_stream=pipelines, **auth_params))

        return streams
