import json
import random
from .logger import log
from yaml import safe_load


def get_curl_cmd(url, token):
    json_data = {
        "kind": "TokenReview",
        "apiVersion": "authentication.k8s.io/v1beta1",
        "spec": {"token": token},
    }
    return "curl -X POST -H 'Content-Type: application/json' \
           -d '{}' {}".format(
        json.dumps(json_data), url
    )


async def get_hostname(one_master):
    cmd = "hostname -i"
    output = await one_master.run(cmd, timeout=15)
    assert output.status == "completed"
    return output.results.get("Stdout", "").strip()


async def get_valid_token(one_master):
    output = await one_master.run("cat /home/ubuntu/config")
    assert output.status == "completed"
    kubeconfig = safe_load(output.results.get("Stdout", ""))
    assert "users" in kubeconfig
    return kubeconfig["users"][0]["user"]["token"]


async def verify_service(one_master):
    cmd = "systemctl is-active cdk.master.auth-webhook.service"
    output = await one_master.run(cmd)
    assert output.status == "completed"
    assert output.results.get("Stdout", "").strip() == "active"


async def verify_auth_success(one_master, cmd):
    output = await one_master.run(cmd)
    assert output.status == "completed"
    assert "authenticated:true" in output.results.get("Stdout", "").replace('"', "")


async def verify_auth_failure(one_master, cmd):
    output = await one_master.run(cmd)
    assert output.status == "completed"
    assert "authenticated:false" in output.results.get("Stdout", "").replace('"', "")


async def verify_custom_auth(one_master, cmd, endpoint):
    output = await one_master.run(cmd)
    assert output.status == "completed"

    # make sure expected custom log entry is present
    output = await one_master.run(
        "grep Forwarding /root/cdk/auth-webhook/auth-webhook.log"
    )
    assert output.status == "completed"
    assert (
        "Forwarding to: {}".format(endpoint) in output.results.get("Stdout", "").strip()
    )


async def test_validate_auth_webhook(model, tools):
    # This test verifies the auth-webhook service is working
    log("starting auth-webhook test")
    masters = model.applications["kubernetes-control-plane"]
    k8s_version_str = masters.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    if k8s_minor_version < (1, 17):
        log("skipping, k8s version v" + k8s_version_str)
        return

    one_master = random.choice(masters.units)
    hostname = await get_hostname(one_master)
    await verify_service(one_master)

    # Verify authn with a valid token
    log("verifying valid token")
    valid_token = await get_valid_token(one_master)
    good_curl = get_curl_cmd("https://{}:5000/v1beta1".format(hostname), valid_token)
    await verify_auth_success(one_master, good_curl)

    # Verify no auth with an invalid token
    log("verifying invalid token")
    invalid_token = "this_cant_be_right"
    bad_curl = get_curl_cmd("https://{}:5000/v1beta1".format(hostname), invalid_token)
    await verify_auth_failure(one_master, bad_curl)

    try:
        # Verify invalid token triggers a call to a custom endpoint
        log("verifying custom endpoint")
        ep = "https://localhost:6000/v1beta1"
        await masters.set_config({"authn-webhook-endpoint": ep})
        log("waiting for cluster to settle...")
        await tools.juju_wait()
        await verify_custom_auth(one_master, bad_curl, ep)
    finally:
        # Reset config
        await masters.set_config({"authn-webhook-endpoint": ""})
        log("waiting for cluster to settle...")
        await tools.juju_wait()
