#include <cinolib/meshes/trimesh.h>
#include <cinolib/meshes/hexmesh.h>
#include <cinolib/voxelize.h>
#include <cinolib/voxel_grid_to_hexmesh.h>
#include <cinolib/grid_projector.h>
#include <iostream>
#include <chrono>
int main(int argc,char**argv){
 if(argc<5){std::cerr<<"input.obj resolution project_iterations output.mesh\n";return 2;}
 try{
  auto t=std::chrono::steady_clock::now();
  cinolib::Trimesh<> s(argv[1]);
  cinolib::VoxelGrid g;
  cinolib::voxelize(s,std::stoul(argv[2]),g);
  cinolib::Hexmesh<> h;
  cinolib::voxel_grid_to_hexmesh(g,h);
  std::cout<<"RAW vertices "<<h.num_verts()<<" hex "<<h.num_polys()<<std::endl;
  h.save((std::string(argv[4])+".raw.mesh").c_str());
  unsigned n=std::stoul(argv[3]);
  if(n){cinolib::GridProjectorOptions o;o.max_iter=n;o.SJ_thresh=0.05;
   std::cout<<"PROJECTOR residual "<<cinolib::grid_projector(h,s,o)<<std::endl;}
  h.save(argv[4]);
  std::cout<<"FINAL vertices "<<h.num_verts()<<" hex "<<h.num_polys()<<" seconds "<<std::chrono::duration<double>(std::chrono::steady_clock::now()-t).count()<<std::endl;
  return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}
}
