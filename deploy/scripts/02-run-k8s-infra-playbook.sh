#!/bin/bash


set -exu

if [ -z ${BASE_WORKING_DIR} ]; then
  echo "BASE_WORKING_DIR environment variable is not set!"
  exit 1
fi
# Stack User Home Directory
export DEPLOY_DIR_NAME="kuhl-haus-mdp-deployment"
export ANSIBLE_SRC_DIR="${BASE_WORKING_DIR}/${DEPLOY_DIR_NAME}/ansible"

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


cd "${SRC_DEST}" || exit 1

sudo -EHn -u stack ansible-playbook -vv -i inventories/"${APP_ENV}"/ "playbooks/k8s-infra.yml" \
    --extra-vars="@group_vars/secrets.yml" \
    --extra-vars="@group_vars/all.yml"

