import matplotlib.pyplot as plt
import numpy as np


def closest_distance(node, nodes: list) -> np.array:
    """Get shortest between a node and a list of nodes (that includes the given
    node)"""
    nodes = np.asarray(nodes)
    dist_2 = np.linalg.norm(nodes - node, axis=1)
    return np.sort(dist_2)[1]


def filter_nav_items_by_proximity(items, min_sep: float = 5.0) -> np.array:
    """Filter navigator items (markers) if they are within `min_sep` micrometer
    of another one."""
    ret = []
    stagecoords = np.array([item.stage_xy for item in items])
    for i, coord in enumerate(stagecoords):
        try:
            min_dist = closest_distance(coord, stagecoords)
        except IndexError:
            min_dist = np.inf

        if min_dist > min_sep:
            ret.append(items[i])

    return ret


def calc_total_dist(coords: list, route: list = None) -> float:
    """Calculate the total distance over a list of (x,y) coordinates.

    route, list[int]
        List of integers with the same length as `coords` that specifies
        the order of the items

    Returns:
        total_dist, float
            Total distance for the given path
    """
    if route is None:
        diffs = np.diff(coords, axis=0)
    else:
        diffs = np.diff(coords[route], axis=0)

    # TODO: add backlash in diffs/total_dist calculation
    total_dist = np.linalg.norm(diffs, axis=1).sum()

    return total_dist


def two_opt_swap(r: list, i: int, k: int) -> list:
    """Reverses items `i`:`k` in the list `r`
    https://en.wikipedia.org/wiki/2-opt."""
    out = r.copy()
    out[i:k + 1] = out[k:i - 1:-1]
    return out


def two_opt(coords: list, threshold: float, verbose: bool = False) -> list:
    """Implementation of the two_opt algorithm for finding the shortest path
    through a list of coordinates (x, y)
    https://en.wikipedia.org/wiki/2-opt."""
    route = np.arange(len(coords))
    improvement = 1
    initial_distance = best_distance = calc_total_dist(coords, route)
    while improvement > threshold:
        previous_best_distance = best_distance
        for i in range(1, len(route) - 2):
            for k in range(i + 1, len(route)):
                new_route = two_opt_swap(route, i, k)
                new_distance = calc_total_dist(coords, new_route)
                if new_distance < best_distance:
                    route = new_route
                    best_distance = new_distance
        improvement = 1 - best_distance / previous_best_distance
    if verbose:
        diff = initial_distance - best_distance
        perc = diff / initial_distance
        print(f'Optimized path for {len(coords)} items from {initial_distance/1000:.1f} to {best_distance/1000:.1f} μm (-{perc:.2%})')

    return route


def sort_nav_items_by_shortest_path(items: list,
                                    first: int = 0,
                                    threshold: float = 0.1,
                                    plot: bool = False,
                                    ) -> list:
    """Find shortest route based on stage coordinates (.stage_xy)

    Parameters
    ----------
    items : list
        List of navigation items with stage coordinates (item.stage_xy)
    first : int or tuple
        If first is an integer, it is the index of the object to start from, must be 0 <= x < len(items)
        If it is a tuple, it should contain the stage coordinates, e.g. the last known coordinate, the function will figure out
        the closest coordinate to start from.
    threshold : float
        Number between 0.0 and 1.0 that determines when convergence is reached. If the improvement is smaller than the threshold, the algorithm will accept convergence.
    plot : bool
        Plot the resulting Path

    Returns
    -------
        List of navigation items sorted to minimize total path distance
    """
    try:
        coords = np.array([item.stage_xy for item in items])
        is_nav = True
    except AttributeError:
        coords = items
        is_nav = False

    if not isinstance(first, int):  # assume it is a coordinate
        first = np.array(first)
        first = np.argmin(np.linalg.norm(coords - first, axis=1))
        print(f'First = {first}')

    if first > 0:
        coords = np.concatenate((coords[first:first + 1], coords[0:first], coords[first + 1:]))

    route = two_opt(coords, threshold, verbose=True)

    if plot:
        fig, (ax0, ax1) = plt.subplots(ncols=2, figsize=(12, 6))
        new_coords = coords[route]
        ax0.set_title(f'Before, total distance: {calc_total_dist(coords)/1000:.3g} μm')
        ax0.plot(coords[:, 0] / 1000, coords[:, 1] / 1000, 'r-', marker='o')
        ax0.scatter(coords[0, 0] / 1000, coords[0, 1] / 1000, color='red', s=100)
        ax0.axis('equal')
        ax1.set_title(f'After, total distance: {calc_total_dist(new_coords)/1000:.3g} μm')
        ax1.plot(new_coords[:, 0] / 1000, new_coords[:, 1] / 1000, 'r-', marker='o')
        ax1.scatter(new_coords[0, 0] / 1000, new_coords[0, 1] / 1000, color='red', s=100)
        ax1.axis('equal')
        plt.show()

    if is_nav:
        return [items[i] for i in route]
    else:
        return items[route]
