"""Estimate connected structures on source-node sections, preserving parent ways."""
from collections import Counter


def estimate(ways, nodes, node_tags, level, cut_nodes, cut_chains, chain_of, water):
    from osm_extract import estimate_structures, is_structure
    incidence = Counter(ref for _,kind,refs,_ in ways if kind == "road" for ref in set(refs))
    loop_refs = {ref for _,kind,refs,_ in ways if kind == "road" and refs and refs[0] == refs[-1] for ref in refs}
    next_id = max((identity for identity,_,_,_ in ways),default=0)+1
    pieces, parents, ranges, grouped = [], {}, {}, {}
    original = {identity:(refs,tags) for identity,kind,refs,tags in ways if kind == "road"}
    for identity,kind,refs,tags in ways:
        if kind != "road":
            pieces.append((identity,kind,refs,tags));continue
        # Explicit elevations and closed source graphs keep their admission
        # path. Sections add no coordinates or graph connections.
        cuts = [0,len(refs)-1]
        if refs and not loop_refs.intersection(refs) and not any("ele" in node_tags.get(ref,{}) for ref in refs):
            cuts = [0]+[i for i in range(1,len(refs)-1) if incidence[refs[i]]>1]+[len(refs)-1]
        grouped[identity]=[]
        for index,(start,end) in enumerate(zip(cuts,cuts[1:])):
            part = identity if index == 0 else next_id
            if index:next_id+=1
            parents[part]=identity;ranges[part]=(start,end);grouped[identity].append(part)
            pieces.append((part,kind,refs[start:end+1],tags))
    local_cut,local_chain=set(),{}
    estimates,leveled=estimate_structures(pieces,nodes,node_tags,
        {part for part,parent in parents.items() if parent in level},cut_nodes,local_cut,local_chain,water)
    cut_chains.update(parents[part] for part in local_cut)
    flat={parent for parent,parts in grouped.items() if all(part in leveled for part in parts)}
    result,sections={},{}
    for parent,parts in grouped.items():
        if not any(part in estimates for part in parts):continue
        refs,tags=original[parent]
        # A structural source is indivisible for failure reporting. Never turn
        # an unresolved piece of an explicit bridge into a ground road.
        if is_structure(tags) and not all(part in estimates for part in parts):continue
        if len(parts)==1:
            result[parent]=estimates[parts[0]]
            chain_of[parent]=parents[local_chain[parts[0]]]
            continue
        values=[]
        for part in parts:
            start,end=ranges[part]
            if part in estimates:
                points,kind=estimates[part]
                values.append(dict(points=points,kind=kind,chain=parents[local_chain[part]]))
            else:
                values.append(dict(points=[(*nodes[ref],0.,ref) for ref in refs[start:end+1]],kind="ground"))
        sections[parent]=values
    return result,flat,sections
