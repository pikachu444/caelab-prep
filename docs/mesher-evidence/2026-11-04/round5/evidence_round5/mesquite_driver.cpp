#include <MeshImpl.hpp>
#include <UntangleWrapper.hpp>
#include <ShapeImprover.hpp>
#include <MsqError.hpp>
#include <iostream>
using namespace Mesquite;
int main(int argc,char**argv){if(argc!=3)return 2;MsqError e;MeshImpl m;m.read_vtk(argv[1],e);if(e){std::cerr<<e;return 3;}m.mark_skin_fixed(e);if(e){std::cerr<<e;return 4;}MeshDomainAssoc a(&m,nullptr);UntangleWrapper u;u.set_cpu_time_limit(120);u.set_outer_iteration_limit(20);u.run_instructions(&a,e);if(e){std::cerr<<e;e.clear();}ShapeImprover s;s.set_cpu_time_limit(120);s.run_instructions(&a,e);if(e){std::cerr<<e;e.clear();}m.write_vtk(argv[2],e);if(e){std::cerr<<e;return 5;}return 0;}
