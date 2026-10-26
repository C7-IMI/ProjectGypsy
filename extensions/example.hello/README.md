# example.hello

Safe reference extension for the isolated self-extension pipeline.

- Action hello prints EXTENSION_HELLO_OK and exits 0.
- Action fail prints EXTENSION_EXPECTED_FAILURE to stderr and exits 3 on purpose.

The manifest's second test expects a nonzero exit, so extension test only passes when the
runner actually detects a failing action. To try it:

```text
python workstream/gypsy.py extension validate example.hello
python workstream/gypsy.py extension test example.hello
python workstream/gypsy.py extension register example.hello --accept
python workstream/gypsy.py extension run example.hello --action hello
```

The fail action is expected to make extension run exit nonzero; that is the point of the
negative test, not a defect.
