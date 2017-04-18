"""
This is a small module which defines an API for downloading resources from the web within a time-limited context. In
other words, while `requests.get` allows you to download something off the web, `limited_requests.limited_get` allows
you to download it off the web, but only if it does so successfully within <timeout> seconds (and, if the file provides
content-length information in its header, the file itself is of <sizeout> size).
"""

import requests
import multiprocessing as mp
import sys


import pdb; pdb.set_trace()
# TODO: UN-HARDCODE THIS!!!!!!!!
sys.path.append("../src/glossarizers/datafy")
import datafy


class FileTooLargeException(Exception):
    """
    This exception is meant to be thrown when sizeout is specified, the URI has a content-length header, and the
    content-length header specifies a filesize larger than sizeout.
    """
    pass


def _fetch(uri, q, reducer, sizeout=None):

    if sizeout:
        r = requests.head(uri)
        if 'content-length' in r.headers:
            if 'content-length' > sizeout:
                raise FileTooLargeException

    dataset_tuples = datafy.get(uri)
    # print(dataset_tuples)  # for debugging
    q.put(reducer(dataset_tuples))


def _size_up(dataset_reprs):
    dataset_representations = []
    for repr in dataset_reprs:
        dataset_representations.append({
            'filesize': sys.getsizeof(repr['data'].content),
            'dataset': repr['fp'],
            'mimetype': repr['mime'],
            'extension': repr['ext']
        })

    return dataset_representations


def q():
    return mp.Queue()


def limited_get(uri, q, reducer=_size_up, timeout=60, sizeout=None):
    """
    Implemented a timed request. Note: this function blocks.

    Parameters
    ----------
    uri: str
        The resource URI.
    q: mp.Queue
        An `mp.Queue` object for message passing. For ease of use initialzie using `q = limited_requests.q()`.
    reducer: func
        A function to be run after a resource is successfully downloaded. When this occurs, the resource is returned in
        the format generated by the `datafy.get` function call: [(<data>, <type string>), ...], a list of tuples. The
        reducer should input this representation and return what you want to get out of the data (probably a list of
        "other stuff"). The default reducer is `_size_up`, which returns filesize information.
    timeout: int
        The maximum amount of time that this entire process will get. If the process takes longer than this, a SIGINT
        will be raised to interrupt and kill the process and move on. This, the crux of the whole problem addressed
        by this module, is done in order to avoid getting stuck on inordinately large files (for which sizeout can't
        be specified).
    sizeout: int, default None
        The maximum size. Note that this parameter will only work for resources which define a `content-length` header.

    Returns
    -------
    Whatever you get by reducing the URI, assuming the job completes. None, if the job doesn't complete.
    """
    p = mp.Process(target=_fetch, args=(uri, q), kwargs={'reducer': reducer, 'sizeout': sizeout})
    p.start()
    p.join(timeout)
    p.terminate()
    # If the process succeeded the exitcode is 0.
    if p.exitcode == 0:
        repr = q.get()
        for dataset in repr:
            dataset['resource'] = uri
        return repr
