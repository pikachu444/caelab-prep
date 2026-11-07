from pathlib import Path
import json,subprocess,time,hashlib
p=Path(__file__).parent.resolve();s=(p/'cad_query.cpp').read_text();s=s.replace('#include <BRep_Builder.hxx>','#include <BRep_Builder.hxx>\n#include <BRepExtrema_DistShapeShape.hxx>\n#include <BRepBuilderAPI_MakeVertex.hxx>\n#include <TopoDS_Compound.hxx>\n#include <cmath>')
s=s.replace('    if (solids.empty()) throw std::runtime_error("CAD has no solid");','')
start=s.index('    const double tol = argc > 2 ?');end=s.index('  } catch (const Standard_Failure& e)')
s=s[:start]+'''    const double tol = argc > 2 ? std::stod(argv[2]) : 1e-9;
    if (!(tol > 0)) throw std::runtime_error("Tolerance must be positive");
    // A compound of boundary FACES, never a solid: interior points must have
    // positive boundary distance instead of the solid-containment zero result.
    TopoDS_Compound boundary; BRep_Builder builder; builder.MakeCompound(boundary);
    int faces=0;
    for(TopExp_Explorer it(shape,TopAbs_FACE);it.More();it.Next()) {builder.Add(boundary,it.Current());++faces;}
    if(faces==0) throw std::runtime_error("No CAD boundary faces");
    BRepExtrema_DistShapeShape distance; distance.SetMultiThread(false); distance.SetDeflection(tol); distance.LoadS1(boundary);
    std::cerr << "{\\"ready\\":true,\\"faces\\":" << faces << ",\\"boundary_compound_not_solid\\":true}\\n";
    double x,y,z; size_t count=0;
    while(std::cin >> x >> y >> z) {
      const gp_Pnt query(x,y,z); distance.LoadS2(BRepBuilderAPI_MakeVertex(query).Vertex());
      if(!distance.Perform() || !distance.IsDone() || distance.NbSolution()<1 || distance.InnerSolution())
        throw std::runtime_error("Boundary distance failed or unexpected interior solution at query " + std::to_string(count));
      const double d=distance.Value(); const gp_Pnt closest=distance.PointOnShape1(1);
      if(!std::isfinite(d) || d<0 || std::abs(query.Distance(closest)-d)>1e-6)
        throw std::runtime_error("Distance/witness inconsistency at query " + std::to_string(count));
      std::cout << std::setprecision(17) << d << ' ' << closest.X() << ' ' << closest.Y() << ' ' << closest.Z()
                << ' ' << int(distance.SupportTypeShape1(1)) << std::endl;
      ++count;
    }
    std::cerr << "{\\"queries\\":" << count << "}\\n";
    return 0;
''' + s[end:]
(p/'cad_boundary_query.cpp').write_text(s);r=json.loads((p/'build_provenance.json').read_text());cmd=r['command'];cmd[4]=str(p/'cad_boundary_query.cpp');cmd[6]=str(p/'cad_boundary_query');t=time.monotonic()
with (p/'boundary_build.log').open('w')as f:x=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
r.update(command=cmd,returncode=x.returncode,seconds=time.monotonic()-t,source_sha256=hashlib.sha256((p/'cad_boundary_query.cpp').read_bytes()).hexdigest());r.pop('binary_sha256',None)
if x.returncode==0:r['binary_sha256']=hashlib.sha256((p/'cad_boundary_query').read_bytes()).hexdigest()
(p/'boundary_build_provenance.json').write_text(json.dumps(r,indent=2));print(x.returncode)
