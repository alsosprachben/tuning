// nvrender: the program -- its whole is the library's (nvrender.cpp, nv_render_main)
extern "C" int nv_render_main(int argc, char **argv);
int main(int argc, char **argv) { return nv_render_main(argc, argv); }
