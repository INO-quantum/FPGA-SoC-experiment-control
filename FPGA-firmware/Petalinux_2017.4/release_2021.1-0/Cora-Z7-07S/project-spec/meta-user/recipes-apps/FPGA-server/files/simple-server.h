////////////////////////////////////////////////////////////////////////////////////////////////////
// simple-server.h
// a simple server class which allows to create easily client and server applications
// created 02/06/2018 by Andi
// compiled with Visual Studio Express 2013 and g++
// tested with Windows 7, Ubuntu 18.04 LTS and Petalinux 2017.4
////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef SIMPLE_SERVER_HEADER
#define SIMPLE_SERVER_HEADER

#include "common.h"                                 // cross-platform macros

//#include <memory>                                 // std::shared_ptr, weak_ptr and std::make_shared
#include "list.h"                                   // single linked list of clients

#ifndef _WINDOWS                                    // LINUX

// class emulating kbhit() and getch()
// requires <stdlib.h>, <string.h>, <unistd.h>, <sys/select.h>, <termios.h>
// if used create static member in cpp file: struct termios conio::old_attributes;
class conio {
private:
    static struct termios old_attributes;
public:
    static void reset(void);                        // reset console
    static void init(void);                         // init console
    static int kbhit(void);                         // returns nonzero if keyboard pressed
    static int getch(void);                         // get keyboard key (<0 on error)
};

#endif

// error codes
// special error codes must be within SERVER_ERROR + [0,0x0ff], others start with SERVER_ERROR + 0x100
#define SERVER_ERROR            0x0C00                  // simple_server error codes start with this
#define SERVER_SEND_PENDING     (SERVER_ERROR + 0x5A)   // SendData could not send all data in one package, 
                                                        // onSendFinished() will be called when finished or error.
#define SERVER_WAIT_TIMEOUT     (SERVER_ERROR + 0x20)   // waiting timeout

#define ETHERNET_MSS            1460                // Ethernet max. segement size in bytes = max. payload/frame
#define RECV_BUFLEN             (1024*512)          // (512kB) length of receive buffer in bytes. if this is too small writing to DMA memory becomes very slow.
#define RECV_MARGIN             32                  // margin when new receive buffer is allocated (0 if none, i.e. fill all buffers completely)
#define RECV_MULTIPLE           8                   // if >1 ensures each buffer has multiple of RECV_MULTIPLE bytes regardless of RECV_MARGIN 
                                                    // ensure RECV_BUFLEN is multiple of RECV_MULTIPLE

#define CLIENT_FLAG_CLIENT      0                   // client created with connect
#define CLIENT_FLAG_SERVER      1                   // server created with listen

// return values by onData, ONDATA_USER_BITS are ignored and everything else is treated as ON_DATA_CLOSE_CLIENT.
#define ONDATA_FREE_LAST        0x00000             // last buffer can be freed (expect no more data)
#define ONDATA_FREE_ALL         0x10000             // all buffers can be freed (expect no more data)
#define ONDATA_REUSE_LAST       0x20000             // last buffer can be reused (expect more data)
#define ONDATA_REUSE_ALL        0x30000             // all buffers can be reused (expect more data)
#define ONDATA_IN_USE_LAST      0x40000             // last data is kept by onData (free from app)
#define ONDATA_IN_USE_ALL       0x50000             // all data is kept by onData (free from app)
#define ONDATA_COLLECT_LAST     0x60000             // collect last buffer of data (expect more data)
#define ONDATA_COLLECT_ALL      0x70000             // collect all buffers of data (expect more data)
#define ONDATA_CLOSE_CLIENT     0x90000             // close client (recommended on error)
#define ONDATA_USER_BITS        0x0ffff             // user bits are ignored by server

// single-linked list of large data to be sent by client
class send_data {
    friend single_linked_list<send_data>;           // allow single_linked list to access 'next'
private:
    send_data *next;
    void *data;
    int bytes;
    int sent;

public:
    send_data(void *data, int bytes, int bytes_sent);
    ~send_data();

    void *get_data(void) { return data; };                // get data
    void *get_reset_data(void) { void *d = data; data = NULL; bytes = sent = 0; return d; }; // get and reset data
    int get_bytes(void) { return bytes; };                // get number of bytes to be sent
    int get_sent(void) { return sent; };                // get number of bytes already sent
    int get_remaining(void) { return (bytes - sent); };        // get number of remaining bytes to be sent

    int update(int sent_next) { sent += sent_next; return (bytes - sent); }; // adds sent_next to sent and returns remaining bytes to be sent
};

// single-linked list of received data given to onData
class recv_data {
    friend single_linked_list<recv_data>;                // allow single_linked list to access 'next'
private:
    recv_data *next;                        // next entry in single linked list
    char *data;                            // data
    int bytes;                            // number of bytes

public:
    recv_data(char *data, int bytes);
    ~recv_data();

    char *get_data(void) { return data; };                  // get data
    char *get_reset_data(void) { char *d = data; data = NULL; bytes = 0; return d; }; // get and reset data
    char *exchange(char *data, int bytes) { char *d = this->data; this->data = data; this->bytes = bytes; return d; }; // exchange data
    int get_bytes(void)  { return bytes; };                 // get number of bytes to be sent
    int update(int add_bytes) { bytes += add_bytes; return bytes; }; // add (or subtract) add_bytes and return new number of bytes
    void reset_bytes(void) { bytes = 0; }                   // reset bytes to 0
};

// client information stored in single-linked list
class client_info {
    friend single_linked_list<client_info>;                // allow single_linked list to access 'next'

private:
    client_info *next;                        // pointer to next client or NULL
    SOCKET socket;                            // client socket
    char *IP_address;                        // IP address of client
    char *port_str;                            // port string of client
    unsigned short port_ushort;                    // port ushort of client
    unsigned int flags;                        // see CLIENT_FLAG_ constant
    int recv_bytes;                            // total number of received bytes
    
    // copy port in string and ushort form. returns true on success.
    bool set_port(unsigned short port);
    bool set_port(const char *port);

public:
    void *client_data;                        // application specific data. free in onDisconnect.

    // constructor with IP_address and port copied and destructor
    client_info(const char *IP_address, const char *port, unsigned int flags);
    client_info(const char *IP_address, unsigned short port, unsigned int flags);
    ~client_info();

    // returns type of client
    bool is_client(void);
    bool is_server(void);
    bool is_local(void);                        // returns true if local IP_address

    // set/get and close socket
    void set_socket(SOCKET socket);
    SOCKET get_socket(void) { return socket; };
    void close_socket(void);

    // get IP address and port
    char *get_IP_address(void) { return IP_address;    };
    char *get_port_str(void) { return port_str;    };
    unsigned short get_port_ushort(void) { return port_ushort; };

    // get local port to which socket is bound and update
    unsigned short get_local_port(bool update);

    // lists of received data and data to be sent
    single_linked_list<recv_data> recv;                // list of data received    
    single_linked_list<send_data> send;                // list of data to be sent
    int recv_get_bytes(void) { return recv_bytes; };        // return total number of received bytes
    int recv_add_bytes(int add_bytes) { recv_bytes += add_bytes; return recv_bytes; }; // add add_bytes and return total number of received bytes
    void recv_delete_all(void);                    // savely deletes recv list
    void send_delete_all(void);                    // savely deletes send list

    /* data receiving
    void recv_append(recv_data *next) { recv.append(next); };
    recv_data *recv_get_first(void) { return recv.get_first(); };
    recv_data *recv_get_last(void) { return recv.get_last(); };    
    bool recv_remove(recv_data *next) { return recv.deleteEntry(next); };
    void recv_empty(void) { recv.deleteAll(); };

    // data sending
    bool is_sending(void) { return (!send.is_empty()); };
    void send_append(send_data *next) { send.append(next); };
    send_data *send_get(void) { return send.get_first(); };
    bool send_remove(send_data *next) { return send.deleteEntry(next); };
    void send_empty(void) { send.deleteAll(); };*/
};

class simple_server {
private:
    unsigned long timeout;                        // timeout in ms onTimeout is called
    THREAD_HANDLE thread;                        // thread handle
    volatile int error;                        // error code of Shutdown
    volatile bool startup;                        // true after startup is finished
    volatile bool running;                        // true while server is running

    // private helper functions
    int AcceptClient(client_info *server);                // accept client if onConnect() returns true
    int ReceiveData(client_info *&client);                 // receives data from client
    int SendNextData(client_info *client);                // send next data to client
#ifdef USE_LINK
    int ThreadCom(client_info *client, void *data, int num);     // received num bytes of data from a thread
#endif

    // server loop
    int SelectLoop(void);

    // server thread start routine
    static THREAD_ENTRY(server_thread,class simple_server *info);

protected:
    // list of clients
    single_linked_list<client_info> clients;

    // client functions
    // note: typical use in onStartup to create a client (connect) or server (listen)
    int connect(const char *IP_address, const char *port);        // creates a client and connects to given IP address and port
    int listen(const char *IP_address, const char *port, int maxclients);    // creates server and listens at IP_address and port for maximum maxclients clients

    // send data
    int SendData(client_info *client, void *data, int *num);    // send num bytes of data to client

    // application specific server/client events
    // notes: 
    // - all exectued by server thread
    // - call Shutdown() or thread_Shutdown() to quit server
    virtual void onStartup(void) = 0;                // server startup
    virtual bool onConnect(client_info *c) = 0;            // client has connected to server. return true to accept client.
    virtual void onTimeout(void) = 0;                // called every timeout ms. use for timing
    virtual void onSendFinished(client_info *client, void *data, int num, int sent, int error) = 0;    // sending of large data finished
    virtual void onDisconnect(client_info *c) = 0;             // client disconnected
    virtual void onShutdown(int error) = 0;                // server shutdown with error code (0=ok)
    // received tot_bytes > 0 bytes of data from client/server. return one of the ONDATA_ values.
    // last_buffer and last_bytes are the last entries of the receive list - obtained with c->recv.get_last().
    // if tot_bytes == last_bytes then the receive list contains only one entry, otherwise contains more entries.
    // first entry of list can be obtained with first = c->recv.get_first(),
    // successive entries can be obtained with c->recv.get_next(first).
    virtual int onData(client_info *c, char *last_buffer, int last_bytes, int tot_bytes) = 0;

    // shutdown of server thread with given error code.
    int shutdown(int error);

public:
    // static member
    static const char localhost[];                    // name "localhost"
    static const char localhost_IPv4[];                // name "127.0.0.1"

    // constructor and destructor
    simple_server();
    ~simple_server();

    // info functions
    // note: not thread safe but for most cases should not matter
    bool is_running(void) { return running; };            // returns true if server thread is running
    unsigned long get_timeout(void) { return timeout; };        // returns timeout in ms

    // start or stop server thread
    // all return 0 if ok, otherwise error code
    // note: called from master thread
    int thread_start(unsigned long timeout);            // starts new server thread with timeout in ms onTimeout is called
    int thread_shutdown(unsigned long timeout);            // shutdown server and wait for its termination
    int thread_wait_shutdown(void);                    // wait until server terminates
    int thread_wait_startup(unsigned poll_ms);            // wait until server startup

    // inter-thread communication
    // these functions can be called from other threads
    static client_info * thread_connect(const char *IP_address, const char *port); // connect to IP_address:port

    static int thread_send(client_info *client, void *data, int num, int timeout_ms);// send num bytes of data to client
    static int thread_recv(client_info *client, char *buffer, int length);        // receive data from client

    static int thread_disconnect(client_info *client);        // disconnect client

    static int thread_wait_send(SOCKET s, int timeout_ms);         // waits until last sending of data is finished
    static int thread_wait_recv(SOCKET s, int timeout_ms);         // waits until data is available

};


#endif // SIMPLE_SERVER_HEADER
