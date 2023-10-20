from pipen import Pipen, Proc


class P(Proc):
    """Process"""
    input = "in"
    input_data = [1]
    output = "out:var:{{in.in}}"
    script = "echo 123"


class Pipeline(Pipen):
    """The pipeline"""
    starts = P


if __name__ == "__main__":
    Pipeline().run()
