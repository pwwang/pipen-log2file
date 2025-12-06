from dotenv import load_dotenv
from pipen import Proc, Pipen

load_dotenv()
BUCKET = "gs://handy-buffer-287000.appspot.com"


class ExampleProc(Proc):
    input = "in"
    output = "out:var:{{in.in}}"
    script = "echo 1"


class ExamplePipelineCloudWdir(Pipen):
    starts = ExampleProc
    # cache = False
    data = [["a", "b", "c", "d", "e"]]
    workdir = f"{BUCKET}/pipen-log2file-example"
    loglevel = "debug"
    cache = False


if __name__ == "__main__":
    ExamplePipelineCloudWdir(plugins=["log2file"]).run()
