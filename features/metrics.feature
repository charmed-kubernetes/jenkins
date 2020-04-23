Feature: Enable metrics on the K8S Cluster

  Scenario: Turn metrics on and off on kubernetes-master
    Given we disable/enable metrics in the charm config
    Then we make sure the metrics-server is started and stopped appropriately
