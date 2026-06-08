#!/bin/bash

###############################################################################
#
# FUNCTIONS
#
###############################################################################
run_test_cmd_with_retry() {

    TEST_CMD=$1
    EXPECTED_RESULT=$2
    counter=$3
    sleep_for=$4
    echo "================================================================================"
    echo "= "
    echo "= TEST_CMD: ${TEST_CMD}"
    echo "= EXPECTED_RESULT: ${EXPECTED_RESULT}"
    echo "= RETRIES: ${counter}"
    echo "= SLEEP: ${sleep_for}"
    echo "= "
    echo "================================================================================"

    while [ $counter -gt 0 ]
    do
        RESULT=$(eval $TEST_CMD)
        echo "${RESULT}"
        if [[ $RESULT == *"${EXPECTED_RESULT}"* ]]; then
            echo "TEST PASSED"
            counter=0
            return 0
        fi
        echo "TEST FAILED"
        if [ $counter -gt 1 ]; then
            echo "Will try again in $sleep_for seconds..."
            sleep $sleep_for
        fi

        counter=$(( $counter - 1 ))
    done
    echo "MAX RETRY COUNT REACHED"
    SHOULD_EXIT_WITH_CODE=1

}

###############################################################################
#
# MAIN
#
###############################################################################
SHOULD_EXIT_WITH_CODE=0

if [ -z ${MDQ_SERVER_DOMAIN} ]; then
  echo "MDQ_SERVER_DOMAIN environment variable is not set!"
  exit 1
fi


run_test_cmd_with_retry 'curl -s -o /dev/null -w "%{http_code}" https://${MDQ_SERVER_DOMAIN}/' '200' 60 5
run_test_cmd_with_retry "curl https://${MDQ_SERVER_DOMAIN}/" "RabbitMQ Management" 60 5 || SHOULD_EXIT_WITH_CODE=1

echo "EXITING WITH ${SHOULD_EXIT_WITH_CODE}"
echo "EOF"

exit $SHOULD_EXIT_WITH_CODE
