from collections import deque

citations = [
    ("A", "B"),
    ("A", "C"),
    ("B", "C"),
    ("D", "A"),
    ("D", "C"),
]

graph = {}

for citing, cited in citations:
    if citing not in graph:
        graph[citing] = []

    if cited not in graph:
        graph[cited] = []

    graph[citing].append(cited)

expected = {
    "A": ["B", "C"],
    "B": ["C"],
    "C": [],
    "D": ["A", "C"]
}

assert graph == expected

def out_degree(graph, case):
    return len(graph[case])


assert out_degree(graph, "A") == 2
assert out_degree(graph, "B") == 1
assert out_degree(graph, "C") == 0
assert out_degree(graph, "D") == 2


def in_degree(graph, case):
    count = 0
    for cases in graph:
        for cited in graph[cases]:
            if cited == case:
                count+=1
    return count

assert in_degree(graph, "A") == 1
assert in_degree(graph, "B") == 1
assert in_degree(graph, "C") == 3
assert in_degree(graph, "D") == 0

def most_cited(graph):
    max = 0
    mostCited = "-1"
    for cases in graph:
        if in_degree(graph, cases) > max:
            max = in_degree(graph, cases)
            mostCited = cases
    return mostCited

def dfs_helper(graph, node, visited):
    visited.add(node)

    for neighbor in graph[node]:
        if neighbor not in visited:
            dfs_helper(graph, neighbor, visited)

def dfs(graph, start):
    visited = set()

    def visit(node):
        visited.add(node)

        for neighbor in graph[node]:
            if neighbor not in visited:
                visit(neighbor)

    visit(start)
    return visited

def bfs(graph, start):
    visited = set()
    queue = deque([start])

    while queue:
        node = queue.popleft()

        if node not in visited:
            visited.add(node)

            for neighbor in graph[node]:
                if neighbor not in visited:
                    queue.append(neighbor)

    return visited

def shortest_path(graph, start, target):
    parent = {start: None}
    visited = {start}
    queue = deque([start])

    while queue:
        node = queue.popleft()

        if node == target:
            return parent

        for neighbor in graph[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                parent[neighbor] = node
                queue.append(neighbor)

    return None
