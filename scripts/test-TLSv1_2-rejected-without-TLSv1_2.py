# Author: Hubert Kario, (c) 2016
# Released under Gnu GPL v2.0, see LICENSE file for details

"""Minimal test for verifying DHE_RSA key exchange support"""

from __future__ import print_function
import traceback
import sys
import getopt
from itertools import chain, islice

from tlsfuzzer.runner import Runner
from tlsfuzzer.messages import Connect, ClientHelloGenerator, \
        ClientKeyExchangeGenerator, ChangeCipherSpecGenerator, \
        FinishedGenerator, ApplicationDataGenerator, AlertGenerator
from tlsfuzzer.expect import ExpectServerHello, ExpectCertificate, \
        ExpectServerHelloDone, ExpectChangeCipherSpec, ExpectFinished, \
        ExpectAlert, ExpectClose, \
        ExpectApplicationData

from tlslite.constants import CipherSuite, AlertLevel, AlertDescription, \
        ExtensionType
from tlsfuzzer.utils.lists import natural_sort_keys


version = 2


def help_msg():
    print("Usage: <script-name> [-h hostname] [-p port] [[probe-name] ...]")
    print(" -h hostname    name of the host to run the test against")
    print("                localhost by default")
    print(" -p port        port number to use for connection, 4433 by default")
    print(" probe-name     if present, will run only the probes with given")
    print("                names and not all of them, e.g \"sanity\"")
    print(" -e probe-name  exclude the probe from the list of the ones run")
    print("                may be specified multiple times")
    print(" -n num         only run `num` random tests instead of a full set")
    print("                (\"sanity\" tests are always executed)")
    print(" --help         this message")


def main():
    """Test if server supports the DHE_RSA key exchange"""
    host = "localhost"
    port = 4433
    num_limit = None
    run_exclude = set()

    argv = sys.argv[1:]
    opts, args = getopt.getopt(argv, "h:p:e:n:", ["help"])
    for opt, arg in opts:
        if opt == '-h':
            host = arg
        elif opt == '-p':
            port = int(arg)
        elif opt == '-e':
            run_exclude.add(arg)
        elif opt == '-n':
            num_limit = int(arg)
        elif opt == '--help':
            help_msg()
            sys.exit(0)
        else:
            raise ValueError("Unknown option: {0}".format(opt))

    if args:
        run_only = set(args)
    else:
        run_only = None

    conversations = {}

    # sanity check
    conversation = Connect(host, port)
    node = conversation
    ciphers = [CipherSuite.TLS_RSA_WITH_AES_128_CBC_SHA]
    node = node.add_child(ClientHelloGenerator(ciphers,
                                               extensions={ExtensionType.
                                                   renegotiation_info:None}))
    node = node.add_child(ExpectServerHello(version=(3, 3),
                                            extensions={ExtensionType.
                                                     renegotiation_info:None}))
    node = node.add_child(ExpectCertificate())
    #node = node.add_child(ExpectServerKeyExchange())
    node = node.add_child(ExpectServerHelloDone())
    node = node.add_child(ClientKeyExchangeGenerator())
    node = node.add_child(ChangeCipherSpecGenerator())
    node = node.add_child(FinishedGenerator())
    node = node.add_child(ExpectChangeCipherSpec())
    node = node.add_child(ExpectFinished())
    node = node.add_child(ApplicationDataGenerator(
        bytearray(b"GET / HTTP/1.0\n\n")))
    node = node.add_child(ExpectApplicationData())
    node = node.add_child(AlertGenerator(AlertLevel.warning,
                                         AlertDescription.close_notify))
    node = node.add_child(ExpectAlert())
    node.next_sibling = ExpectClose()

    conversations["sanity"] = conversation

    # sanity check - TLS 1.1 enabled
    conversation = Connect(host, port)
    node = conversation
    ciphers = [CipherSuite.TLS_RSA_WITH_AES_128_CBC_SHA]
    node = node.add_child(ClientHelloGenerator(ciphers,
                                               version=(3, 2),
                                               extensions={ExtensionType.
                                                   renegotiation_info:None}))
    node = node.add_child(ExpectServerHello(version=(3, 2),
                                            extensions={ExtensionType.
                                                     renegotiation_info:None}))
    node = node.add_child(ExpectCertificate())
    #node = node.add_child(ExpectServerKeyExchange())
    node = node.add_child(ExpectServerHelloDone())
    node = node.add_child(ClientKeyExchangeGenerator())
    node = node.add_child(ChangeCipherSpecGenerator())
    node = node.add_child(FinishedGenerator())
    node = node.add_child(ExpectChangeCipherSpec())
    node = node.add_child(ExpectFinished())
    node = node.add_child(ApplicationDataGenerator(
        bytearray(b"GET / HTTP/1.0\n\n")))
    node = node.add_child(ExpectApplicationData())
    node = node.add_child(AlertGenerator(AlertLevel.warning,
                                         AlertDescription.close_notify))
    node = node.add_child(ExpectAlert())
    node.next_sibling = ExpectClose()

    conversations["sanity"] = conversation

    # check TLSv1.2 ciphers without TLSv1.2 client hello
    for cipher in [CipherSuite.TLS_DHE_RSA_WITH_AES_128_CBC_SHA256,
                   CipherSuite.TLS_DHE_RSA_WITH_AES_256_CBC_SHA256,
                   CipherSuite.TLS_DHE_RSA_WITH_AES_128_GCM_SHA256,
                   CipherSuite.TLS_DHE_RSA_WITH_AES_256_GCM_SHA384,
                   CipherSuite.TLS_RSA_WITH_AES_128_CBC_SHA256,
                   CipherSuite.TLS_RSA_WITH_AES_256_CBC_SHA256,
                   CipherSuite.TLS_RSA_WITH_AES_128_GCM_SHA256,
                   CipherSuite.TLS_RSA_WITH_AES_256_GCM_SHA384]:
        conversation = Connect(host, port)
        node = conversation
        ciphers = [cipher]
        node = node.add_child(ClientHelloGenerator(ciphers,
                                                   version=(3, 2),
                                                   extensions={ExtensionType.
                                                       renegotiation_info:None}))
        node = node.add_child(ExpectAlert(AlertLevel.fatal,
                                          AlertDescription.handshake_failure))
        node.add_child(ExpectClose())

        conversations[CipherSuite.ietfNames[cipher] + " in TLSv1.1"] =\
                conversation

    # run the conversation
    good = 0
    bad = 0
    failed = []
    if not num_limit:
        num_limit = len(conversations)

    # make sure that sanity test is run first and last
    # to verify that server was running and kept running throught
    sanity_test = ('sanity', conversations['sanity'])
    ordered_tests = chain([sanity_test],
                          islice(filter(lambda x: x[0] != 'sanity',
                                        conversations.items()), num_limit),
                          [sanity_test])

    for c_name, c_test in ordered_tests:
        if run_only and c_name not in run_only or c_name in run_exclude:
            continue
        print("{0} ...".format(c_name))

        runner = Runner(c_test)

        res = True
        try:
            runner.run()
        except Exception:
            print("Error while processing")
            print(traceback.format_exc())
            res = False

        if res:
            good += 1
            print("OK\n")
        else:
            bad += 1
            failed.append(c_name)

    print("Script to verify that server does not negotiate TLS1.2 ciphers")
    print("in TLS1.1 or earlier protocol")
    print("version: {0}\n".format(version))

    print("Test end")
    print("successful: {0}".format(good))
    print("failed: {0}".format(bad))
    failed_sorted = sorted(failed, key=natural_sort_keys)
    print("  {0}".format('\n  '.join(repr(i) for i in failed_sorted)))

    if bad > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
