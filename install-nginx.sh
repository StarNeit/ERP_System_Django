# Read this: https://github.com/mdirolf/nginx-gridfs
# Read this: http://www.thegeekstuff.com/2011/07/install-nginx-from-source/
# Read this: http://stackoverflow.com/questions/22667200/nginx-fails-to-make-with-submodule-os-x-10-9

wget http://nginx.org/download/nginx-1.8.0.tar.gz
tar zxvf nginx-1.8.0.tar.gz
rm -fr nginx-1.8.0.tar.gz
git clone https://github.com/mdirolf/nginx-gridfs.git
cd nginx-gridfs/
git submodule init
git submodule update
wget http://sourceforge.net/projects/pcre/files/pcre/8.37/pcre-8.37.tar.gz/download
cd pcre-8.37/
./configure --prefix=/usr/local
make
sudo make install
cd ../nginx-1.8.0
./configure --add-module=../nginx-gridfs/
make 
sudo make install
