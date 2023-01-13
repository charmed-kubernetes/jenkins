import asyncio
import urllib.request
from .logger import log
from bs4 import BeautifulSoup as bs
from .utils import juju_run


def find_nagios_criticals(url, opener):
    url_data = opener.open(url)
    soup = bs(url_data.read(), "html.parser")
    return soup.find_all("td", class_="statusBGCRITICAL")


async def wait_for_no_errors(url, opener):
    criticals = ["dummy"]
    while len(criticals) > 0:
        criticals = find_nagios_criticals(url, opener)
        await asyncio.sleep(30)


async def test_nagios(model, tools):
    # This test verifies the nagios relation is working
    # properly. This requires:
    # 1) Deploy nagios and nrpe
    # 2) login to nagios
    # 3) verify things settle and no errors
    # 4) force api server issues
    # 5) verify nagios errors show for master and worker
    # 6) fix api server
    # 7) break a worker's kubelet
    # 8) verify nagios errors for worker
    # 9) fix worker

    log("starting nagios test")
    masters = model.applications["kubernetes-control-plane"]
    k8s_version_str = masters.data["workload-version"]
    k8s_minor_version = tuple(int(i) for i in k8s_version_str.split(".")[:2])
    if k8s_minor_version < (1, 17):
        log("skipping, k8s version v" + k8s_version_str)
        return

    # 1) deploy
    log("deploying nagios and nrpe")
    nagios = await model.deploy("nagios", series="bionic")
    await model.deploy(
        "nrpe", series="bionic", config={"swap": "", "swap_activity": ""}, num_units=0
    )
    await nagios.expose()
    await model.add_relation("nrpe", "kubernetes-control-plane")
    await model.add_relation("nrpe", "kubernetes-worker")
    await model.add_relation("nrpe", "etcd")
    await model.add_relation("nrpe", "easyrsa")
    await model.add_relation("nrpe", "kubeapi-load-balancer")
    await model.add_relation("nagios", "nrpe")
    log("waiting for cluster to settle...")
    await tools.juju_wait()

    # 2) login to nagios
    cmd = "cat /var/lib/juju/nagios.passwd"
    output = await juju_run(nagios.units[0], cmd, timeout=10)
    login_passwd = output.stdout.strip()

    pwd_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    url_base = "http://{}".format(nagios.units[0].public_address)
    pwd_mgr.add_password(None, url_base, "nagiosadmin", login_passwd)
    handler = urllib.request.HTTPBasicAuthHandler(pwd_mgr)
    opener = urllib.request.build_opener(handler)
    status_url = "{}/cgi-bin/nagios3/status.cgi?host=all".format(url_base)

    # 3) wait for nagios to settle
    log("waiting for nagios to settle")
    await wait_for_no_errors(status_url, opener)

    # 4) break all the things
    log("breaking api server")
    await masters.set_config({"api-extra-args": "broken=true"})

    # 5) make sure nagios is complaining for kubernetes-control-plane
    #    AND kubernetes-worker
    log("Verifying complaints")
    criticals = []
    while True:
        criticals = find_nagios_criticals(status_url, opener)

        if criticals:
            found_master = []
            found_worker = []
            for c in criticals:
                for link in c.find_all("a", recursive=False):
                    if "kubernetes-control-plane" in link.string:
                        found_master.append(link.string)
                    elif "kubernetes-worker" in link.string:
                        found_worker.append(link.string)
            if found_master and found_worker:
                log("Found critical errors:")
                for s in found_master + found_worker:
                    log(" - {}".format(s))
                break
        await asyncio.sleep(30)

    # 6) fix api and wait for settle
    log("Fixing API server")
    await masters.set_config({"api-extra-args": ""})
    await wait_for_no_errors(status_url, opener)

    # 7) break worker
    log("Breaking workers")
    workers = masters = model.applications["kubernetes-worker"]
    await workers.set_config({"kubelet-extra-args": "broken=true"})

    # 8) verify nagios is complaining about worker
    log("Verifying complaints")
    criticals = []
    while True:
        criticals = find_nagios_criticals(status_url, opener)

        if criticals:
            found_worker = []
            for c in criticals:
                for link in c.find_all("a", recursive=False):
                    if "kubernetes-worker" in link.string:
                        found_worker.append(link.string)
                        break
            if found_worker:
                log("Found critical errors:")
                for s in found_worker:
                    log(" - {}".format(s))
                break
        await asyncio.sleep(30)

    # 9) Fix worker and wait for complaints to go away
    await workers.set_config({"kubelet-extra-args": ""})
    await wait_for_no_errors(status_url, opener)
