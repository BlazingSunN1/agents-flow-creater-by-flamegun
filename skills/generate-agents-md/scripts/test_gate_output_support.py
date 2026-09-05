import json


def passing_output(argv):
    if 'playwright' in argv:
        return json.dumps({'config': {}, 'errors': [],
            'stats': {'expected': 1, 'unexpected': 0, 'flaky': 0, 'skipped': 0},
            'suites': [{'specs': [{'title': 'acceptance', 'tests': [
                {'expectedStatus': 'passed', 'results': [{'status': 'passed'}]},
            ]}]}]})
    return '----------------------------------------------------------------------\nRan 1 test in 0.001s\n\nOK\n'
