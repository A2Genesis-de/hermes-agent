#!/usr/bin/env bash
# OLD and NEW must stamp the checked-out source, not the CI driver's ref.
# A subshell preserves the workflow's identity and the git URL redirect.
source_build_env() (
  unset GITHUB_SHA GITHUB_REF GITHUB_REF_NAME GITHUB_HEAD_REF GITHUB_BASE_REF
  unset A2ASSISTANT_BUILD_COMMIT A2ASSISTANT_PAYLOAD_TAG A2ASSISTANT_PAYLOAD_VERSION A2ASSISTANT_DESKTOP_VARIANT
  "$@"
)