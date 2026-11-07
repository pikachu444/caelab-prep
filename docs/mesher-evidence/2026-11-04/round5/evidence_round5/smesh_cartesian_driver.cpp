#include <BRepTools.hxx>
#include <BRep_Builder.hxx>
#include <BRepCheck_Analyzer.hxx>
#include <SMESH_Gen.hxx>
#include <SMESH_Mesh.hxx>
#include <SMESHDS_Mesh.hxx>
#include <SMDS_MeshElement.hxx>
#include <SMDS_MeshNode.hxx>
#include <SMDS_VolumeTool.hxx>
#include <StdMeshers_Cartesian_3D.hxx>
#include <StdMeshers_CartesianParameters3D.hxx>
#include <iostream>
#include <fstream>
#include <iomanip>
#include <map>
#include <vector>
#include <string>
int main(int argc,char**argv){if(argc!=4)return 2;TopoDS_Shape sh;BRep_Builder b;if(!BRepTools::Read(sh,argv[1],b)){std::cerr<<"BRep import failed";return 3;}auto*g=new SMESH_Gen;auto*m=g->CreateMesh(false);m->ShapeToMesh(sh);auto*a=new StdMeshers_Cartesian_3D(g->GetANewId(),g);auto*h=new StdMeshers_CartesianParameters3D(g->GetANewId(),g);for(int axis=0;axis<3;++axis){std::vector<std::string> f{argv[2]};std::vector<double>p;h->SetGridSpacing(f,p,axis);}h->SetSizeThreshold(4.0);h->SetToAddEdges(true);h->SetToCreateFaces(true);m->AddHypothesis(sh,a->GetID());m->AddHypothesis(sh,h->GetID());bool ok=g->Compute(*m,sh);auto*ds=m->GetMeshDS();std::map<int,long long> inv;for(auto i=ds->elementsIterator();i->more();)++inv[int(i->next()->GetEntityType())];std::ofstream o(std::string(argv[3])+".json");o<<"{\"computed\":"<<(ok?"true":"false")<<",\"CAD_valid\":"<<(BRepCheck_Analyzer(sh).IsValid()?"true":"false")<<",\"nodes\":"<<m->NbNodes()<<",\"volumes\":"<<m->NbVolumes()<<",\"entity_inventory\":{";bool first=true;for(auto p:inv){if(!first)o<<",";first=false;o<<"\""<<p.first<<"\":"<<p.second;}o<<"}}\n";std::ofstream raw(std::string(argv[3])+".raw");raw<<std::setprecision(17)<<"NODES "<<m->NbNodes()<<"\n";for(auto i=ds->nodesIterator();i->more();){auto*n=i->next();raw<<n->GetID()<<" "<<n->X()<<" "<<n->Y()<<" "<<n->Z()<<"\n";}raw<<"ELEMENTS\n";for(auto i=ds->elementsIterator();i->more();){auto*e=i->next();raw<<e->GetID()<<" "<<int(e->GetEntityType())<<" "<<e->getshapeId()<<" "<<e->NbNodes();for(int j=0;j<e->NbNodes();++j)raw<<" "<<e->GetNode(j)->GetID();raw<<"\n";}raw<<"VOLUME_FACES\n";for(auto i=ds->elementsIterator(SMDSAbs_Volume);i->more();){auto*e=i->next();SMDS_VolumeTool t(e);raw<<e->GetID()<<" "<<t.NbFaces();for(int f=0;f<t.NbFaces();++f){auto**nodes=t.GetFaceNodes(f);int n=t.NbFaceNodes(f);raw<<" "<<n;for(int j=0;j<n;++j)raw<<" "<<nodes[j]->GetID();}raw<<"\n";}return ok?0:4;}
