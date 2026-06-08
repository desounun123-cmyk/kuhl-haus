#!/bin/bash

PLAYBOOK="playbooks/deploy-app.yml"  # Default playbook if none specified

# Handle named arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --playbook=*)
      PLAYBOOK="${1#*=}"
      shift
      ;;
    *)
      # If first parameter doesn't start with --, treat it as playbook name
      if [[ $1 != --* ]] && [[ -z $PLAYBOOK_POS ]]; then
        PLAYBOOK_POS="$1"
        shift
      else
        echo "Unknown parameter: $1"
        exit 1
      fi
      ;;
  esac
done

# Positional parameter overrides the default or named parameter
if [[ -n $PLAYBOOK_POS ]]; then
  PLAYBOOK="$PLAYBOOK_POS"
fi

# If playbook doesn't have a directory path, prepend "playbooks/"
if [[ $PLAYBOOK != */* ]]; then
  PLAYBOOK="playbooks/$PLAYBOOK"
fi


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


set -exu

if [ -z ${BASE_WORKING_DIR} ]; then
  echo "BASE_WORKING_DIR environment variable is not set!"
  exit 1
fi
# Stack User Home Directory
export DEPLOY_DIR_NAME="kuhl-haus-mdp-deployment"
export ANSIBLE_SRC_DIR="${BASE_WORKING_DIR}/${DEPLOY_DIR_NAME}/ansible"
export VERSION_DIR_NAME="kuhl-haus-mdp-app"
export VERSION_SRC_DIR="${BASE_WORKING_DIR}/${VERSION_DIR_NAME}"

ls -hal

if [ -z "${APP_ENV}" ]; then
    echo "APP_ENV environment variable is not set!"
    exit 1
fi

USER_HOME="/home/stack"
SRC_DEST="${USER_HOME}/mdp"

if [ ! -d "${USER_HOME}" ]; then
    echo "${USER_HOME} does not exist!"
    exit 1
fi

if [ -d "${SRC_DEST}" ]; then
    echo "${SRC_DEST} exists! Removing pre-exising data..."
    rm -rf "${SRC_DEST}"
fi

mkdir -pv "${SRC_DEST}"
cp -af "${ANSIBLE_SRC_DIR}"/. "${SRC_DEST}"
chown -R stack:stack "${SRC_DEST}"
ls -hal "${SRC_DEST}"

# Calculate the image tag in the same way as build-images.sh
# Working in the VERSION_SRC_DIR to access the pyproject.toml and git repo
cd "${VERSION_SRC_DIR}" || exit 1

IMAGE_TAG=$(get_image_tag)

cd "${SRC_DEST}" || exit 1

sudo -EHn -u stack ansible-playbook -vv -i inventories/"${APP_ENV}"/ "${PLAYBOOK}" \
    --extra-vars="@group_vars/secrets.yml" \
    --extra-vars="@group_vars/all.yml" \
    --extra-vars="app_container_image_version=${IMAGE_TAG}"

