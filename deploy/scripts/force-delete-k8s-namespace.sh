#!/bin/bash


usage() {
    echo "Usage:"
    echo "  $0 <namespace>"
    echo
    echo "Examples:"
    echo "  $0 mattermost"
    exit 1
}

if [ $# -ne 1 ]; then  
    echo "Error: Expected namespace value"
    usage
fi

export NS=$1

# Validate required parameters
if [ -z "$NS" ]; then
    echo "Error: Expected namespace value"
    usage
fi

function count_apiresources() {
  resource=$1
  ROWS=$(kubectl get $resource -n $NS -o name |wc -l);
  echo $ROWS
  return $ROWS
}

function patch_apiresources(){
  resource=$1
  for resource_name in $(kubectl get $resource -n $NS -o name); do
    echo "Patch $resource $resource_name"
    kubectl -n $NS patch $resource_name -p '{"metadata":{"finalizers":null}}' --type=merge
  done
}

function delete_apiresources(){
  resource=$1
  for resource_name in $(kubectl get $resource -n $NS -o name); do
    echo "Delete $resource $resource_name"
    kubectl -n $NS delete $resource_name --force
  done
}

function patch_delete_apiresources(){
  API_RESOURCE=$1
  ROWS=$(count_apiresources $API_RESOURCE)
  if [ $ROWS -gt 0 ]; then
    echo Patch $ROWS occurences of api-resource $API_RESOURCE for $NS to remove finalizers
    patch_apiresources $API_RESOURCE
    ROWS=$(count_apiresources $API_RESOURCE)
    if [ $ROWS -gt 0 ]; then
      echo Delete $ROWS occurences of api-resource $API_RESOURCE for $NS
      delete_apiresources $API_RESOURCE
    else
      echo No occurences of api-resource $API_RESOURCE left.
    fi
  else
    echo No occurences of api-resource $API_RESOURCE found...
  fi
}



for API_RESOURCE in $(kubectl api-resources --no-headers --verbs=list --namespaced -o name); do
  patch_delete_apiresources $API_RESOURCE
done
 

echo Patch namespace $NS to clear metadata.finalizers 
kubectl patch ns $NS -p '{"metadata":{"finalizers":null}}'
echo Patch namespace $NS to clear spec.finalizers 
kubectl patch ns $NS -p '{"spec":{"finalizers":null}}'
echo Patch namespace $NS to clear metadata.annotations
kubectl patch ns $NS -p '{"metadata":{"annotations":null}}'
echo Force delete namespace $NS
kubectl delete ns $NS --grace-period=0 --force

