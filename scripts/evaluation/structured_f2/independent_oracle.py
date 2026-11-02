"""Independent ASCII MSH4, analytical lattice and finite-element quality oracle.

Does not import recipe geometry helpers or Gmsh. Prepared-family checks only.
"""
from collections import Counter, defaultdict
import itertools
import math
from pathlib import Path

def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(k,a): return tuple(k*x for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a,a))
def unit(a): return mul(1/norm(a),a)
def distance(a,b): return norm(sub(a,b))
def cyclic(a): return min(tuple(a[i:]+a[:i]) for i in range(len(a)))

SIDES_Q=((0,1),(1,2),(2,3),(3,0))
SIDES_H=((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
EDGES_H=SIDES_Q+((4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7))
SIGNS=((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))

def parse_msh(path):
    lines=Path(path).read_text().splitlines()
    sections={};i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('$') and not line.startswith('$End'):
            name=line[1:];end=lines.index('$End'+name,i+1);sections[name]=lines[i+1:end];i=end
        i+=1
    assert sections['MeshFormat'][0].split()[:2]==['4.1','0'],'ASCII MSH4.1 required'
    entities={};data=iter(sections['Entities']);counts=list(map(int,next(data).split()))
    for dim,count in enumerate(counts):
        for _ in range(count):
            row=next(data).split();at=4 if dim==0 else 7;nphys=int(row[at])
            entities[(dim,int(row[0]))]=tuple(map(int,row[at+1:at+1+nphys]))
    tokens=iter(' '.join(sections['Nodes']).split())
    blocks,total,minimum,maximum=[int(next(tokens)) for _ in range(4)];nodes={}
    for _ in range(blocks):
        dim,tag,parametric,n=[int(next(tokens)) for _ in range(4)]
        tags=[int(next(tokens)) for _ in range(n)]
        for tag in tags:
            xyz=tuple(float(next(tokens)) for _ in range(3))
            if parametric:
                for _ in range(dim): next(tokens)
            assert tag not in nodes,'duplicate node ID'
            assert all(math.isfinite(x) for x in xyz),'nonfinite node'
            nodes[tag]=xyz
    assert len(nodes)==total
    assert next(tokens,None) is None
    data=iter(sections['Elements']);blocks,total,minimum,maximum=map(int,next(data).split());elements={}
    inventory=Counter()
    for _ in range(blocks):
        dim,entity,typ,n=map(int,next(data).split())
        for _ in range(n):
            row=list(map(int,next(data).split()));eid,*conn=row
            assert eid not in elements,'duplicate element ID'
            assert all(node in nodes for node in conn),'unresolved connectivity'
            assert len(set(conn))==len(conn),'repeated node within element'
            elements[eid]={'type':typ,'dim':dim,'nodes':tuple(conn),'physical':entities[(dim,entity)]}
        inventory[(dim,typ,len(conn))]+=n
    assert len(elements)==total
    assert next(data,None) is None
    return nodes,elements,[dict(dimension=d,type=t,arity=a,count=n) for (d,t,a),n in sorted(inventory.items())]

def source_patches(spec):
    if 'patches' in spec:
        return [(p['divisions'],[spec['vertices'][key] for key in p['corners']]) for p in spec['patches']]
    return [(spec['divisions'],spec['corners'])]

def expected_lattices(spec,expect):
    mode=spec['mode']
    if mode=='line':
        a,b=spec['points'];n=spec['divisions']
        return [[add(a,mul(i/n,sub(b,a))) for i in range(n+1)]]
    if mode=='arc':
        c=spec['center'];u=unit(sub(spec['start'],c));w=unit(cross(u,sub(spec['end'],c)));v=cross(w,u)
        radius,theta=expect['radius'],expect['angle'];n=spec['divisions']
        return [[add(c,add(mul(radius*math.cos(theta*i/n),u),mul(radius*math.sin(theta*i/n),v))) for i in range(n+1)]]
    output=[]
    for (nx,ny),p in source_patches(spec):
        layer_count=spec['layers'] if mode=='hex' else 0
        points=[]
        for k in range(layer_count+1):
            for j in range(ny+1):
                t=j/ny
                for i in range(nx+1):
                    s=i/nx
                    point=add(add(mul((1-s)*(1-t),p[0]),mul(s*(1-t),p[1])),add(mul(s*t,p[2]),mul((1-s)*t,p[3])))
                    if layer_count: point=add(point,mul(k/layer_count,spec['vector']))
                    points.append(point)
        output.append(points)
    return output

def expected_cells(spec,lattices):
    if spec['mode'] in ('line','arc'):
        seq=lattices[0];return [[(seq[i],seq[i+1]) for i in range(len(seq)-1)]]
    result=[]
    for ((nx,ny),_),nodes in zip(source_patches(spec),lattices):
        plane=(nx+1)*(ny+1);layers=spec['layers'] if spec['mode']=='hex' else 1
        cells=[]
        for k in range(layers):
            for j in range(ny):
                for i in range(nx):
                    a=k*plane+j*(nx+1)+i
                    q=(a,a+1,a+nx+2,a+nx+1)
                    if spec['mode']=='hex': q=q+tuple(x+plane for x in q)
                    cells.append(tuple(nodes[x] for x in q))
        result.append(cells)
    return result

def matching_lattices(spec,expect,nodes,active,delta):
    buckets=defaultdict(list)
    def key(p): return tuple(math.floor(x/delta) for x in p)
    for identifier in active: buckets[key(nodes[identifier])].append(identifier)
    out=[];deviation=0.
    for lattice in expected_lattices(spec,expect):
        ids=[]
        for point in lattice:
            base=key(point);matches=[]
            for dx in itertools.product((-1,0,1),repeat=3):
                for identifier in buckets.get(tuple(base[k]+dx[k] for k in range(3)),()):
                    error=distance(point,nodes[identifier])
                    if error<=delta: matches.append((identifier,error))
            assert len(matches)==1,('expected lattice point has missing/duplicate nodes',point,len(matches))
            identifier,error=matches[0];ids.append(identifier);deviation=max(deviation,error)
        assert len(set(ids))==len(ids),'collapsed lattice'
        out.append(ids)
    assert set().union(*map(set,out))==active,'unexpected active node'
    return out,deviation

def topology(top,sides):
    occurrences=defaultdict(list)
    for eid,cell in top.items():
        for indices in sides:
            face=tuple(cell['nodes'][i] for i in indices)
            occurrences[tuple(sorted(face))].append((eid,face))
    adjacency={eid:set() for eid in top}
    for face,rows in occurrences.items():
        assert len(rows) in (1,2),('nonmanifold incidence',face,len(rows))
        if len(rows)==2:
            (a,x),(b,y)=rows
            assert a!=b
            if len(x)==2: assert x==y[::-1],('edge ordering',x,y)
            else: assert cyclic(list(x))==cyclic(list(y[::-1])),('face ordering',x,y)
            adjacency[a].add(b);adjacency[b].add(a)
    reached=set();todo=[next(iter(top))]
    while todo:
        eid=todo.pop()
        if eid not in reached: reached.add(eid);todo.extend(adjacency[eid]-reached)
    assert len(reached)==len(top),'multiple disconnected components'
    return occurrences

def hex_jacobian(p,xi,eta,zeta):
    # Derivative sums vanish; local-origin coordinates avoid subtractive loss.
    p=[sub(point,p[0]) for point in p]
    derivative=[(sx*(1+sy*eta)*(1+sz*zeta)/8,sy*(1+sx*xi)*(1+sz*zeta)/8,sz*(1+sx*xi)*(1+sy*eta)/8) for sx,sy,sz in SIGNS]
    columns=[tuple(sum(p[i][k]*derivative[i][j] for i in range(8)) for k in range(3)) for j in range(3)]
    determinant=dot(columns[0],cross(columns[1],columns[2]))
    denom=math.prod(norm(col) for col in columns)
    assert denom>0,'degenerate Jacobian'
    return determinant,determinant/denom

def verify(case,path,contract):
    spec,expect=case['input'],case['expectation'];mode=spec['mode']
    dim={'line':1,'arc':1,'quad':2,'hex':3}[mode]
    typ,arity={1:(1,2),2:(3,4),3:(5,8)}[dim]
    nodes,elements,inventory=parse_msh(path)
    assert max(e['dim'] for e in elements.values())==dim
    top={eid:e for eid,e in elements.items() if e['dim']==dim}
    assert len(top)==expect['elements'],('element count',len(top),expect['elements'])
    assert all(e['type']==typ and len(e['nodes'])==arity for e in top.values()),'unexpected top-dimensional family/order'
    active=set(n for cell in top.values() for n in cell['nodes'])
    assert len(active)==expect['active_nodes'],('active node count',len(active),expect['active_nodes'])
    if mode=='line': scale=distance(*spec['points'])
    elif mode=='arc': scale=expect['radius']
    else:
        points=[point for _,p in source_patches(spec) for point in p]
        scale=max(distance(a,b) for a,b in itertools.combinations(points,2))
        if mode=='hex': scale=max(scale,norm(spec['vector']))
    delta=contract['coordinate_relative_tolerance']*scale
    lattice_ids,deviation=matching_lattices(spec,expect,nodes,active,delta)
    expected_by_patch=expected_cells(spec,lattice_ids)
    actual_by_nodes={frozenset(cell['nodes']):eid for eid,cell in top.items()}
    assert len(actual_by_nodes)==len(top),'duplicate cells'
    group_ids=[]
    for index,expected in enumerate(expected_by_patch):
        ids=set()
        for conn in expected:
            eid=actual_by_nodes.get(frozenset(conn));assert eid is not None,('missing expected lattice cell',conn)
            actual=top[eid]['nodes'];ids.add(eid)
            assert top[eid]['physical']==(110+index,),('wrong physical source',eid,top[eid]['physical'])
            if dim==1: assert actual==conn,('line ordering',actual,conn)
            elif dim==2: assert cyclic(list(actual))==cyclic(list(conn)),('quad ordering',actual,conn)
            else:
                wanted={frozenset(conn[i] for i in side) for side in SIDES_H}
                got={frozenset(actual[i] for i in side) for side in SIDES_H}
                assert wanted==got,('Hex8 face ordering',eid)
        group_ids.append(ids)
    assert set().union(*group_ids)==set(top),'physical sources not exhaustive'
    if len(group_ids)==2: assert not group_ids[0]&group_ids[1]
    report=dict(elements=len(top),active_nodes=len(active),all_msh_nodes=len(nodes),inventory=inventory,max_lattice_coordinate_error=deviation,coordinate_tolerance=delta,physical_group_cells=[len(s) for s in group_ids],hanging_nodes=0,connected_components=1)
    measure=0.;min_jac=math.inf;min_scaled=math.inf;max_aspect=0.
    if dim==1:
        incidence=Counter(n for cell in top.values() for n in cell['nodes'])
        assert sorted(incidence.values()).count(1)==2 and all(x in (1,2) for x in incidence.values())
        measure=sum(distance(*(nodes[n] for n in cell['nodes'])) for cell in top.values())
        expected_measure=expect.get('polyline_length',expect['measure'])
        if mode=='arc':
            c=spec['center'];r=expect['radius'];u=unit(sub(spec['start'],c));w=unit(cross(u,sub(spec['end'],c)));v=cross(w,u)
            max_angle_error=max_radius_error=max_plane_error=0.
            for i,identifier in enumerate(lattice_ids[0]):
                p=sub(nodes[identifier],c)
                max_radius_error=max(max_radius_error,abs(norm(p)-r));max_plane_error=max(max_plane_error,abs(dot(p,w)))
                angle=math.atan2(dot(p,v),dot(p,u))
                max_angle_error=max(max_angle_error,abs(angle-expect['angle']*i/spec['divisions']))
            assert max_radius_error<=delta and max_plane_error<=delta
            assert max_angle_error<=contract['angle_absolute_tolerance_radians']
            report.update(radius_error=max_radius_error,plane_error=max_plane_error,angle_error=max_angle_error,analytic_arc_length=expect['measure'],analytic_chord_length=expected_measure,polyline_approximation_relative_error=abs(measure-expect['measure'])/expect['measure'])
    else:
        sides=SIDES_Q if dim==2 else SIDES_H
        incidence=topology(top,sides)
        report.update(boundary_sides=sum(len(rows)==1 for rows in incidence.values()),interior_sides=sum(len(rows)==2 for rows in incidence.values()))
        if len(group_ids)==2:
            shared=[face for face,rows in incidence.items() if len(rows)==2 and ((rows[0][0] in group_ids[0]) != (rows[1][0] in group_ids[0]))]
            shared_nodes=set(n for face in shared for n in face)
            assert len(shared)==expect['shared_boundary_cells']
            assert len(shared_nodes)==expect['shared_nodes']
            assert set(lattice_ids[0])&set(lattice_ids[1])==shared_nodes
            report.update(shared_boundary_cells=len(shared),shared_nodes=len(shared_nodes))
        normal=expect['source_normal']
        for cell in top.values():
            p=[nodes[n] for n in cell['nodes']]
            if dim==2:
                measure+=sum(dot(cross(sub(p[i],p[0]),sub(p[i+1],p[0])),normal)/2 for i in (1,2))
                for i in range(4):
                    u,v=sub(p[(i+1)%4],p[i]),sub(p[(i-1)%4],p[i])
                    determinant=dot(cross(u,v),normal)
                    min_jac=min(min_jac,determinant/4);min_scaled=min(min_scaled,determinant/(norm(u)*norm(v)))
                edges=SIDES_Q
            else:
                for location in itertools.product(contract['hex_samples'],repeat=3):
                    jac,scaled=hex_jacobian(p,*location);min_jac=min(min_jac,jac);min_scaled=min(min_scaled,scaled)
                for location in itertools.product((-1/math.sqrt(3),1/math.sqrt(3)),repeat=3):
                    measure+=hex_jacobian(p,*location)[0]
                edges=EDGES_H
            lengths=[distance(p[a],p[b]) for a,b in edges]
            assert min(lengths)>0
            max_aspect=max(max_aspect,max(lengths)/min(lengths))
        assert min_jac>0,('nonpositive Jacobian',min_jac)
        gate=contract['quad_min_corner_signed_scaled_jacobian' if dim==2 else 'hex_min_sampled_scaled_jacobian']
        assert min_scaled>=gate,('scaled Jacobian gate',min_scaled,gate)
        aspect_gate=contract['quad_max_edge_aspect_ratio' if dim==2 else 'hex_max_edge_aspect_ratio']
        assert max_aspect<=aspect_gate,('edge aspect gate',max_aspect,aspect_gate)
        report.update(min_signed_jacobian=min_jac,min_independent_scaled_jacobian=min_scaled,max_edge_aspect_ratio=max_aspect,scaled_jacobian_gate=gate)
        expected_measure=expect['measure']
    relative=abs(measure-expected_measure)/abs(expected_measure)
    assert relative<=contract['relative_measure_tolerance'],('analytic measure mismatch',measure,expected_measure,relative)
    report.update(measure=measure,analytic_measure=expected_measure,relative_measure_error=relative)
    return report
