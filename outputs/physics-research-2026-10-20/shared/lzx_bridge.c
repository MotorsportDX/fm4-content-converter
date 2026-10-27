/* Research bridge to the local LGPL libmspack lzxd.c, loaded as a data decoder.
   No Xbox or game code is executed. Third-party source is not copied here. */
#include <stdlib.h>
#include <string.h>
#include "system.h"
#include "lzx.h"
typedef struct { unsigned char *data; size_t size, pos; } Buffer;
static int rd(struct mspack_file *p,void *out,int n) {
  Buffer *b=(Buffer*)p; size_t take=(size_t)n;
  if(take>b->size-b->pos)take=b->size-b->pos;
  memcpy(out,b->data+b->pos,take); b->pos+=take; return (int)take;
}
static int wr(struct mspack_file *p,void *in,int n) {
  Buffer *b=(Buffer*)p; size_t take=(size_t)n;
  if(take>b->size-b->pos)take=b->size-b->pos;
  memcpy(b->data+b->pos,in,take); b->pos+=take; return (int)take;
}
static void *al(struct mspack_system *s,size_t n){return calloc(1,n);}
static void cp(void *src,void *dst,size_t n){memcpy(dst,src,n);}
__declspec(dllexport) int decode_lzx(unsigned char *src,size_t n,unsigned char *dst,size_t m,int bits) {
  struct mspack_system sys={0}; Buffer in={src,n,0},out={dst,m,0};
  sys.read=rd;sys.write=wr;sys.alloc=al;sys.free=free;sys.copy=cp;
  struct lzxd_stream *stream=lzxd_init(&sys,(struct mspack_file*)&in,(struct mspack_file*)&out,bits,0,32768,m,0);
  if(!stream)return -1;
  int result=lzxd_decompress(stream,m);lzxd_free(stream);
  if(!result && out.pos!=m)return -2;
  return result;
}
