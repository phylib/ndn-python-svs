# Basic Libraries
from argparse import ArgumentParser, SUPPRESS
import asyncio as aio
import sys
import time
import logging
import threading
from typing import Optional
# NDN Imports
from ndn.app import NDNApp
from ndn.encoding import Name
# Custom Imports
sys.path.insert(0,'.')
from svs.svs_socket import SVS_Socket
from storage.sqlite import SqliteStorage

def parse_cmd_args():
    # Command Line Parser
    parser = ArgumentParser(add_help=False,description="An SVS Chat Node capable of syncing with others.")
    requiredArgs = parser.add_argument_group("required arguments")
    optionalArgs = parser.add_argument_group("optional arguments")
    informationArgs = parser.add_argument_group("information arguments")
    # Adding all Command Line Arguments
    requiredArgs.add_argument("-n", "--nodename",action="store",dest="node_name",required=True,help="id of this node in svs")
    optionalArgs.add_argument("-gp","--groupprefix",action="store",dest="group_prefix",required=False,help="overrides config | routable group prefix to listen from")
    informationArgs.add_argument("-h","--help",action="help",default=SUPPRESS,help="show this help message and exit")
    # Getting all Arguments
    vars = parser.parse_args()
    args = {}
    if vars.group_prefix != None:
        args["group_prefix"] = vars.group_prefix
    args["node_id"] = vars.node_name
    return args

class SVS_Thread(threading.Thread):
    def __init__(self, group_prefix:str, node_id:str, sqlite_path:str) -> None:
        threading.Thread.__init__(self)
        self.group_prefix = Name.from_str(group_prefix)
        self.nid = Name.from_str(node_id)
        self.sqlite_path = sqlite_path
        self.storage = None
        self.svs = None
        self.loop = None
        self.app = None
        self.failed = False
    def run(self) -> None:
        def loop_task():
            self.app = NDNApp()
            try:
                self.app.run_forever(after_start=self.function())
            except FileNotFoundError:
                print(f'Error: could not connect to NFD for SVS.')
                self.failed = True
                sys.exit()

        self.loop = aio.new_event_loop()
        aio.set_event_loop(self.loop)
        self.loop.create_task(loop_task())
        self.loop.run_forever()
    async def function(self) -> None:
        self.storage = SqliteStorage(self.sqlite_path)
        self.svs = SVS_Socket(self.app, self.storage, self.group_prefix, self.nid, self.missing_callback)
    def missing_callback(self, missing_list) -> None:
        aio.ensure_future(self.on_missing_data(missing_list))
    async def on_missing_data(self, missing_list) -> None:
        for i in missing_list:
            nid = Name.from_str(i.nid)
            while i.lowSeqNum <= i.highSeqNum:
                content_str = await self.svs.fetchData(nid, i.lowSeqNum)
                if content_str != None:
                    content_str = i.nid + ": " + content_str.decode();
                    sys.stdout.write("\033[K")
                    sys.stdout.flush()
                    print(content_str)
                i.lowSeqNum = i.lowSeqNum + 1
    def get_svs(self) -> Optional[SVS_Socket]:
        return self.svs
    def has_failed(self) -> None:
        return self.failed
class Program:
    def __init__(self, args):
        self.args = args
        self.svs_thread = SVS_Thread(self.args["group_prefix"],self.args["node_id"], self.args["sqlite_path"])
        self.svs_thread.daemon = True
        self.svs_thread.start()
        while self.svs_thread.get_svs() == None:
            time.sleep(0.001)
            if self.svs_thread.has_failed():
                sys.exit()
        self.svs = self.svs_thread.get_svs()
        print(f'SVS chat client started | {self.args["group_prefix"]} - {self.args["node_id"]} |')
    def run(self):
        while True:
            try:
                val = input("")
                sys.stdout.write("\033[F"+"\033[K")
                sys.stdout.flush()
                print("YOU: "+val)
                self.svs.publishData(val.encode())
            except KeyboardInterrupt:
                sys.exit()

def main() -> int:
    default_args = {
        'node_id':None,
        'group_prefix':'/svs',
        'sqlite_path':'~/.ndn/svspy/sqlite3.db',
        'logging_level':'INFO',
        'logging_file': "SVS.log"
    }
    cmd_args = parse_cmd_args()
    args = default_args.copy()
    args.update(cmd_args)
    args["node_id"] = Name.to_str(Name.from_str(args["node_id"]))
    args["group_prefix"] = Name.to_str(Name.from_str(args["group_prefix"]))

    log_levels = {
        'CRITICAL':logging.CRITICAL,
        'ERROR':logging.ERROR,
        'WARNING':logging.WARNING,
        'INFO':logging.INFO,
        'DEBUG':logging.DEBUG
    }
    if args["logging_file"] != None:
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', \
            filename=args["logging_file"]+"."+args["node_id"][1:].replace("/","_"), \
            filemode='w+', \
            level=log_levels[args["logging_level"]])
    else:
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', \
            level=log_levels[args["logging_level"]])

    prog = Program(args)
    prog.run()

if __name__ == "__main__":
    sys.exit(main())