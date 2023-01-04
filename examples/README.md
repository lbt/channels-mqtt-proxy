This is the tutorial code from
https://channels.readthedocs.io/en/stable/tutorial/index.html up to
part 3.

It has been extended as per the main README.

Set up a venv and (as of 3/1/2023) from this examples/ directory use:

    pip install ..[examples]

Then edit settings.py to point to your mqtt server and run;


```python
python3 mysite/manage.py migrate
python3 mysite/manage.py runworker mqtt &
python3 mysite/manage.py runserver
```

