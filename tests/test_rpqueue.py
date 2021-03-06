
from __future__ import print_function
from builtins import range
from past.utils import old_div
import multiprocessing
import threading
import time
import unittest

import rpqueue
print("rpqueue test", rpqueue.__file__)
rpqueue.log_handler.setLevel(rpqueue.logging.CRITICAL)

queue = b'TEST_QUEUE'
queue_str = 'TEST_QUEUE'
default = b'default'

def _start_task_processor(rpqueue=rpqueue):
    t = multiprocessing.Process(target=rpqueue._execute_tasks, args=([queue, default],))
    t.daemon = True
    t.start()
    t2 = multiprocessing.Process(target=rpqueue._handle_delayed, args=(None, None, 60))
    t2.daemon = True
    t2.start()
    return t, t2

saw = multiprocessing.Array('i', (0,))

@rpqueue.task(queue=queue)
def task1(a):
    saw[0] = a

@rpqueue.task(queue=queue_str)
def task1_str(a):
    saw[0] = a

@rpqueue.task(queue=queue, attempts=5, retry_delay=0)
def taskr(v, **kwargs):
    saw[0] = v
    if v < 5:
        taskr.retry(v + 1, **kwargs)

@rpqueue.task(queue=queue, attempts=2, retry_delay=0)
def taskr2(v1, v2, **kwargs):
    if v1 != 0:
        taskr2.retry(v1 - 1, **kwargs)
    else:
        saw[0] = v2

@rpqueue.task(queue=queue)
def taske():
    raise Exception

@rpqueue.task(queue=queue)
def speed():
    saw[0] += 1

@rpqueue.task(queue=queue, retry_delay=0)
def speed2(**kwargs):
    saw[0] += 1
    speed2.retry(**kwargs)

@rpqueue.task(queue=queue, retry_delay=.000001)
def speed3(**kwargs):
    saw[0] += 1
    speed3.retry(**kwargs)

@rpqueue.periodic_task(0, queue=queue, low_delay_okay=True)
def periodic_task():
    saw[0] += 1

@rpqueue.periodic_task(0, queue=queue_str, low_delay_okay=True)
def periodic_task_str():
    saw[0] += 1

@rpqueue.task(queue=queue, save_results=30)
def wait_test(n):
    time.sleep(n)
    return n

@rpqueue.task(queue=queue, save_results=30)
def result_test(n):
    return n

@rpqueue.task
def simple_task(a):
    saw[0] = a

global_wait_test = wait_test

scale = 1000

class TestRPQueue(unittest.TestCase):
    def setUp(self):
        saw[0] = 0
        rpqueue.clear_queue(queue)
        rpqueue.SHOULD_QUIT[0] = 0
        self.t, self.t2 = _start_task_processor()

    def tearDown(self):
        rpqueue.SHOULD_QUIT[0] = 1
        if self.t.is_alive():
            self.t.terminate()
        if self.t2.is_alive():
            self.t2.terminate()
        rpqueue.clear_queue(queue, delete=True)
        task1.execute(1)
        speed.execute()
        speed.execute(delay=5)

    def test_simple_task(self):
        task1.execute(1)
        time.sleep(.25)

        self.assertEquals(saw[0], 1)

    def test_simple_task_str(self):
        task1_str.execute(1)
        time.sleep(0.25)

        self.assertEquals(saw[0], 1)

    def test_delayed_task(self):
        task1.execute(2, delay=3)

        time.sleep(2.75)
        self.assertEquals(saw[0], 0)
        time.sleep(0.5)
        self.assertEquals(saw[0], 2)

    def test_retry_task(self):
        saw[0] = -1
        taskr.execute(0)
        time.sleep(0.5)
        self.assertEquals(saw[0], 4)

        saw[0] = -1
        taskr.execute(1)
        time.sleep(0.5)
        self.assertEquals(saw[0], 5)

    def test_retry_task2(self):
        taskr2.execute(0)
        time.sleep(0.5)
        self.assertEquals(saw[0], 0)

        taskr.execute(1)
        time.sleep(0.5)
        self.assertEquals(saw[0], 5)

    def test_exception_no_kill(self):
        taske.execute()
        time.sleep(.001)
        task1.execute(6)

        time.sleep(1)
        self.assertEquals(saw[0], 6)

    def test_periodic_task(self):
        rpqueue.EXECUTE_TASKS = True
        periodic_task.execute(taskid=periodic_task.name)
        time.sleep(2)
        x = saw[0]
        self.assertTrue(x > 0, x)
        print("\n%.1f tasks/second periodic tasks"%(x/2.0,))

    def test_periodic_task_str(self):
        rpqueue.EXECUTE_TASKS = True
        periodic_task_str.execute(taskid=periodic_task_str.name)
        time.sleep(2)
        x = saw[0]
        self.assertTrue(x > 0, x)
        print("\n%.1f tasks/second periodic tasks"%(x/2.0,))

    def test_z_performance1(self):
        saw[0] = 0
        t = time.time()
        for i in range(scale):
            speed.execute()
        while saw[0] < scale:
            time.sleep(.05)
        s = saw[0]
        dt = time.time() - t
        print("\n%.1f tasks/second injection/running"%(old_div(s,dt),))

    def test_z_performance2(self):
        saw[0] = 0
        t = time.time()
        speed2.execute(_attempts=scale)
        while saw[0] < scale:
            time.sleep(.05)
        s = saw[0]
        dt2 = time.time() - t
        print("%.1f tasks/second sequential retries"%(old_div(s,dt2),))

    def test_z_performance3(self):
        saw[0] = 0
        _scale = old_div(scale, 4)
        t = time.time()
        speed3.execute(_attempts=_scale)
        while saw[0] < _scale:
            time.sleep(.05)
        s = saw[0]
        dt3 = time.time() - t
        print("%.1f tasks/second delayed retries"%(old_div(s,dt3),))

    def test_wait(self):
        wt = wait_test.execute(.01, delay=1)
        self.assertTrue(wt.wait(2))
        time.sleep(1)
        self.assertEquals(wt.result, .01)

        wt = wait_test.execute(2, delay=5)
        self.assertFalse(wt.wait(4))
        self.assertTrue(wt.cancel())

        wt = wait_test.execute(2, delay=5)
        wt.wait(6)
        self.assertFalse(wt.cancel())
        time.sleep(2.1)
        self.assertEquals(wt.result, 2)


    def test_queue_override(self):
        t = result_test.execute(5)
        time.sleep(1)
        self.assertEquals(t.result, 5)

        t = result_test.execute(6, _queue=queue + b'2')
        time.sleep(1)
        self.assertEquals(t.result, None)

    def test_simple_task2(self):
        saw[0] = 0
        simple_task.execute(113)
        time.sleep(.5)
        self.assertEqual(saw[0], 113)

if __name__ == '__main__':
    unittest.main()
