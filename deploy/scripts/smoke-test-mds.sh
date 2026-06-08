#!/bin/bash

###############################################################################
#
# FUNCTIONS
#
###############################################################################
check_image_version() {
    URL=$1
    EXPECTED_TAG=$2
    MAX_RETRIES=$3
    RETRY_DELAY=$4

    echo "================================================================================"
    echo "= "
    echo "= URL: ${URL}"
    echo "= EXPECTED_TAG: ${EXPECTED_TAG}"
    echo "= MAX_RETRIES: ${MAX_RETRIES}"
    echo "= RETRY_DELAY: ${RETRY_DELAY}"
    echo "= "
    echo "================================================================================"

    counter=$MAX_RETRIES

    while [ $counter -gt 0 ]
    do
        # Make the curl request and capture the response
        RESPONSE=$(curl -s "${URL}")
        echo "Response: ${RESPONSE}"

        # Check if the response is valid JSON
        if ! echo "${RESPONSE}" | jq -e . >/dev/null 2>&1; then
            echo "Invalid JSON response received"
            if [ $counter -gt 1 ]; then
                echo "Will try again in $RETRY_DELAY seconds..."
                sleep $RETRY_DELAY
            fi
            counter=$(( $counter - 1 ))
            continue
        fi

        # Extract the image_version field
        IMAGE_VERSION=$(echo "${RESPONSE}" | jq -r '.image_version // empty')

        # Check if image_version was found in the response
        if [ -z "${IMAGE_VERSION}" ]; then
            echo "image_version field not found in response"
            if [ $counter -gt 1 ]; then
                echo "Will try again in $RETRY_DELAY seconds..."
                sleep $RETRY_DELAY
            fi
            counter=$(( $counter - 1 ))
            continue
        fi

        echo "Found image_version: ${IMAGE_VERSION}"

        # Compare with expected tag
        if [ "${IMAGE_VERSION}" = "${EXPECTED_TAG}" ]; then
            echo "TEST PASSED: Image version matches expected tag"
            return 0
        else
            echo "Image version ${IMAGE_VERSION} does not match expected tag ${EXPECTED_TAG}"
            if [ $counter -gt 1 ]; then
                echo "Will try again in $RETRY_DELAY seconds..."
                sleep $RETRY_DELAY
            fi
        fi

        counter=$(( $counter - 1 ))
    done

    echo "TEST FAILED: Max retry count reached, image version never matched expected tag"
    return 1
}

get_image_tag() {
  # Try to get tag from git
  GIT_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "")
  if [ -n "$GIT_TAG" ]; then
    # Remove 'v' prefix if present
    export IMAGE_TAG=${GIT_TAG#v}
    echo "$IMAGE_TAG"
  else
    # Get version from setuptools-scm with no-local-version
    VERSION=$(python3 -c "from setuptools_scm import get_version; print(get_version(local_scheme='no-local-version'))" 2>/dev/null)

    if [ $? -ne 0 ] || [ -z "$VERSION" ]; then
      echo "Error: Could not determine version from setuptools-scm" >&2
      exit 1
    fi

    # Add commit hash as suffix for non-tagged builds
    COMMIT_SHORT=$(git rev-parse --short HEAD)

    # Format: version-hash (e.g., 0.1.1.dev2-a1b2c3d)
    export IMAGE_TAG="${VERSION}-${COMMIT_SHORT}"
    echo "$IMAGE_TAG"
  fi
}

###############################################################################
#
# MAIN
#
###############################################################################
SHOULD_EXIT_WITH_CODE=0

if [ -z "${MDS_SERVER_DOMAIN}" ]; then
  echo "MDS_SERVER_DOMAIN environment variable is not set!"
  exit 1
fi
if [ -z "${BASE_WORKING_DIR}" ]; then
  echo "BASE_WORKING_DIR environment variable is not set!"
  exit 1
fi

export VERSION_DIR_NAME="kuhl-haus-mdp-servers"
export VERSION_SRC_DIR="${BASE_WORKING_DIR}/${VERSION_DIR_NAME}"

cd "${VERSION_SRC_DIR}" || exit 1

IMAGE_TAG=$(get_image_tag) || exit 1

check_image_version "https://${MDS_SERVER_DOMAIN}/health" "${IMAGE_TAG}" 60 5 || SHOULD_EXIT_WITH_CODE=1

echo "EXITING WITH ${SHOULD_EXIT_WITH_CODE}"
echo "EOF"

exit $SHOULD_EXIT_WITH_CODE

# curl https://mds.example.com/health
# {
#     "status": "OK",
#     "container_image": "ghcr.io/kuhl-haus/kuhl-haus-mds-server:0.1.0",
#     "image_version": "0.1.0"
# }
