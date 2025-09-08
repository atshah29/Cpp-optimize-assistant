#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include "sim.h"
#include "cache.h"
#include <iostream>
#include <cstdint>
#include <algorithm>
#include <cmath>





using namespace std;
Cache::Cache(uint32_t blocksize, uint32_t size, uint32_t assoc, uint32_t pref_n, uint32_t pref_m, Cache* lower_level){
    this->blocksize = blocksize;
    this->size = size;
    this->assoc = assoc;
    this->pref_n = pref_n;
    this->pref_m = pref_m;
    this->lower_level = lower_level;

    this->num_sets = size / (blocksize * assoc);
    // this->num_index_bits = std::countr_zero(num_sets);
    // this->num_offset_bits = std::countr_zero(blocksize);
    this->num_index_bits = static_cast<uint32_t> (std::log2(num_sets));
    this->num_offset_bits = static_cast<uint32_t> (std::log2(blocksize));
    this->num_tag_bits = 32 - (num_index_bits + num_offset_bits);

// allocate num_sets, each with assoc ways
    sets.resize(num_sets, std::vector<Way>(assoc));

    // initialize every way as 0/false/invalid etc.
    for (uint32_t i = 0; i < num_sets; i++) {
        for (uint32_t j = 0; j < assoc; j++) {
            sets[i][j].valid = false;
            sets[i][j].dirty = false;
            sets[i][j].tag = 0;
            sets[i][j].lru_counter = j; // Initialize LRU counters (0 is most recently used, assoc-1 is least recently used)
        }
    }

    // Initialize N stream buffers, all with M blocks
    for(uint32_t i = 0; i < pref_n; i++) {
        StreamBuffer buff;
        buff.valid = false;
        buff.head = 0;
        buff.blocks.resize(pref_m,0); // Initialize M blocks
        stream_buffers.emplace_back(buff);
    }
 

    // Initialize statistics
    reads = 0;
    writes = 0;
    read_misses = 0;
    write_misses = 0;
    write_backs = 0;
    prefetches = 0;
    nextLevelDemands=0;
    
}

Cache::Cache(){
    // Default constructor
    blocksize = 0;
    size = 0;
    assoc = 0;
    pref_n = 0;
    pref_m = 0;
    lower_level = nullptr;

    num_sets = 0;
    num_index_bits = 0;
    num_offset_bits = 0;
    num_tag_bits = 0;

    reads = 0;
    writes = 0;
    read_misses = 0;
    write_misses = 0;
    write_backs = 0;
    prefetches = 0;
}
 

bool Cache::access(uint32_t address, char rw){
    uint32_t tag_bits = address >> (32 - num_tag_bits); //shift right to get tag
    uint32_t set_mask = (1 << num_index_bits) - 1; //create mask for index bits
    uint32_t index_bits = (address >> num_offset_bits) & set_mask; //shift right to remove offset bits, then mask to get index bits
    
    bool prefetchHit = false;
    int prefetchIndex = -1;
    
    if (rw == 'r') reads++; else writes++;

    if(pref_n > 0){ //if there is a prefetch
        prefetchIndex = check_prefetch(address);  //check if there is a hit
        prefetchHit = (prefetchIndex != -1); //check_prefetch returns -1 if no hit and a buffer index if hit
    }

    auto& set = sets[index_bits]; // Get the set corresponding to the index

    // Check cache
    for (uint32_t i = 0; i < assoc; i++) { // or for (auto it = set.begin(); it != set.end(); ++it) if using list
        Way& way = set[i]; // Get the way
        if (way.valid && way.tag == tag_bits) { //Ensure way is valid and then check if tags match
            // Cache hit
            if (rw == 'w') way.dirty = true; // Mark dirty on write
            update_lru(index_bits, i); // Update LRU on hit
            // or set.splice(set.begin(), set, it); // if using list
            
            if(prefetchHit){ 
                // Scenario 4: Cache hit + prefetch hit, keep stream buffer in sync (passing buffer index and address)
                fill_prefetch(prefetchIndex, address, false);
            }
            // Scenario 3: Cache hit + prefetch miss - do nothing
            return true;
        }
    }

    // Cache miss, allocate space for requested block 
    uint32_t victim = find_victim(index_bits);  // Find victim way using LRU (either first invalid or LRU)
    Way& v = set[victim]; // Get the victim way
    // or Way&v = set.back(); // if using list


    // Write back if needed
    if (v.valid && v.dirty) {
        
        if (lower_level) { // Write back to lower level if exists
            uint32_t victim_addr = (v.tag << (num_index_bits + num_offset_bits)) | 
                                 (index_bits << num_offset_bits);
            lower_level->access(victim_addr, 'w'); // Write back as a write operation passing address (don't care about block address)
        }
        write_backs++; // Increment write back count
        v.dirty = false; // Clear dirty bit after write back
    }
    
    //Determine how to bring in cache block
    if(prefetchHit){
        // Scenario 2: Cache miss + prefetch hit (bring in from stream buffer) and keep stream buffer in sync
        fill_prefetch(prefetchIndex, address, false);
    }
    else {
        if (lower_level) { // Scenario 1: Cache miss + prefetch miss (bring in from lower level) and prefetch next M consecutive blocks if capable
            lower_level->access(address, 'r');
            nextLevelDemands++;
        }
        if (pref_n > 0) { 
            // Always allow the lowest-level cache to spawn a new stream
            fill_prefetch(stream_buffers.size() - 1, address, true);
        }

        // Update miss stats excluding write misses that hit in the stream buffers
        if (rw == 'r') read_misses++;
        else write_misses++;
    }


    // Install the line (from stream buffer or lower level)
    v.valid = true;
    v.tag = tag_bits;
    v.dirty = (rw == 'w');


    update_lru(index_bits, victim); // Update LRU after installing new line
    // or set.splice(set.begin(), set, --set.end()); // if using list
    return false;
}

uint32_t Cache::find_victim(uint32_t set_index){  //Simplistic approach, not required with list because victim is the last element (set.back())
    // Implement victim selection logic here (LRU)
    std::vector<Way> &set = sets[set_index];
    uint32_t lru_index = 0;
    uint32_t max_lru = set[0].lru_counter;
    for (uint32_t i = 0; i < assoc; i++) { // Find the way with the highest lru_counter (not necessary to look for invalid first)
        if (set[i].lru_counter > max_lru) {
            max_lru = set[i].lru_counter;
            lru_index = i;
        }
    }

    return lru_index; //If invalid is not found, find the index of the largest lru_counter
}

void Cache::update_lru(uint32_t set_index, uint32_t set_way) {  //Update LRU counters (increment each counter less than accessed one except the accessed one which is set to 0)
    auto& set = sets[set_index];                                // Could have used list and just moved the accessed way to the front with set.splice(set.begin(), set, it); where it = --set.end()
    uint32_t oldCounter = set[set_way].lru_counter;          // Store the old counter of the accessed way
    for (uint32_t i = 0; i < assoc; i++) {
        if (i == set_way){ // Accessed way
            set[i].lru_counter = 0;
        } 
        else if(set[i].lru_counter < oldCounter){ // Only increment counters that are less than the accessed way's old counter to maintain order
            set[i].lru_counter++;
        }
    }
}



void Cache::print_cache(const std::string &which_cache) { //Would be easier to do with list because the order is already maintained by the list structure
    printf("\n");
    printf("===== %s contents =====\n", which_cache.c_str());
    for (uint32_t i = 0; i < num_sets; i++) {
        // Collect valid ways
        std::vector<std::pair<uint32_t, uint32_t>> lru_list; // (lru_counter, way_index)
        for (uint32_t j = 0; j < assoc; j++) {
            Way& way = sets[i][j];
            if (way.valid) {
                lru_list.emplace_back(way.lru_counter, j); //store each way's lru counter and index (in given set)
            }
        }

        std::sort(lru_list.begin(), lru_list.end(),
                  [](auto &a, auto &b) { return a.first < b.first; }); //sort the list by lru_counter (first element of pair)

        // Print set index
        printf("set %6u:    ", i);

        // Print ways in MRU → LRU order
        for (auto &[_, way_index] : lru_list) {
            Way& way = sets[i][way_index];
            printf("%x %c   ", way.tag, way.dirty ? 'D' : ' ');
        }
        printf("\n");
    }
}

void Cache::print_stream_buffers(void){
    if(pref_n == 0) return; // No stream buffers to print
    printf("\n");
    printf("===== Stream Buffer(s) contents =====\n");
    for(auto i = stream_buffers.begin() ; i!=stream_buffers.end(); ++i){
        if(i->valid){
            uint32_t headAddress = i->head;
            for(uint32_t j=0; j<pref_m; j++){
                uint32_t blockAddress = i->blocks[(j+headAddress) % pref_m];
                printf(" %x ", blockAddress);
            }
            printf("\n");
        }   
    }
}

int32_t Cache::check_prefetch(uint32_t address){
    uint32_t block_addr = address >> num_offset_bits; // Convert to block address
    
    uint32_t buffer_index = 0;
    for (auto it = stream_buffers.begin(); it != stream_buffers.end(); ++it, ++buffer_index) { //Iterate through all stream buffers in MRU order
        if (it->valid) {
            for (uint32_t i = 0; i < pref_m; i++) {
                if (it->blocks[i] == block_addr) {
                    // Update head to point to the next block (X+1, if available)
                    it->head = (i + 1) % pref_m;
                    return buffer_index; // Return the buffer index
                }
            }
        }
    }
    return -1; // Not found
}



void Cache::fill_prefetch(uint32_t buffer_index, uint32_t address, bool is_new_stream = false){ 
    auto it = stream_buffers.begin();
    std::advance(it, buffer_index);
    uint32_t block_addr = address >> num_offset_bits; // Convert to block address
    
    if (is_new_stream) {
        // Scenario 1: Creating new stream buffer
        // Initialize all blocks in sequence starting from the requested block + 1
        for (uint32_t i = 0; i < pref_m; i++) {
            it->blocks[i] = block_addr + 1 + i;
            prefetches++;
            if (lower_level) {
                uint32_t prefetch_addr = (it->blocks[i] << num_offset_bits);
                lower_level->access(prefetch_addr, 'r');
            }
        }
        it->head = 0; // Reset head for new stream
    } else {
        // Scenarios 2 and 4: Existing stream buffer hit
        // Fill from current head position to maintain sequential nature
        for (uint32_t i = 0; i < pref_m; i++) {
            uint32_t pos = (it->head + i) % pref_m;
            uint32_t expected_block = block_addr + 1 + i;
            
            if (it->blocks[pos] != expected_block) {
                it->blocks[pos] = expected_block;
                prefetches++;
                if (lower_level) {
                    uint32_t prefetch_addr = (it->blocks[pos] << num_offset_bits);
                    lower_level->access(prefetch_addr, 'r');
                }
            }
        }
    }
    
    it->valid = true;
    
    // Move to front (MRU position)
    stream_buffers.splice(stream_buffers.begin(), stream_buffers, it); 
}

void printStats(Cache &L1, Cache &L2){
    printf("\n");
    printf("===== Measurements =====\n");
    printf("a. L1 reads:                   %d\n", L1.get_reads()); 
    printf("b. L1 read misses:             %d\n", L1.get_read_misses());
    printf("c. L1 writes:                  %d\n", L1.get_writes());
    printf("d. L1 write misses:            %d\n", L1.get_write_misses());
    printf("e. L1 miss rate:               %.4f\n", max((float)0.0000,(float)(L1.get_read_misses()+L1.get_write_misses()) / (float)(L1.get_reads() + L1.get_writes())));
    printf("f. L1 writebacks:              %d\n", L1.get_write_backs());
    printf("g. L1 prefetches:              %d\n", L1.get_prefetches());

    printf("h. L2 reads (demand):          %d\n", L1.get_nextLevelDemands());
    printf("i. L2 read misses (demand):    %d\n", L2.get_read_misses());
    printf("j. L2 reads (prefetch):        %d\n", 0); // prefetching is only tested and explored in the last-level cache of the memory hierarchy
    printf("k. L2 read misses (prefetch):  %d\n", 0); //should distinguish incoming demand read requests from incoming prefetch read requests
    printf("l. L2 writes:                  %d\n", L2.get_writes());
    printf("m. L2 write misses:            %d\n", L2.get_write_misses());
    printf("n. L2 miss rate:               %.4f\n", max((float)0.0000,(float)L2.get_read_misses() / (float)L1.get_nextLevelDemands()));
    printf("o. L2 writebacks:              %d\n", L2.get_write_backs());
    printf("p. L2 prefetches:              %d\n", L2.get_prefetches());

    uint32_t memory_traffic;
    if(L2.get_reads() == 0){ // check if l2 exists
        memory_traffic = L1.get_read_misses() + L1.get_write_misses() + L1.get_write_backs() + L1.get_prefetches();
    }
    else{
        memory_traffic = L2.get_read_misses() + L2.get_write_misses() + L2.get_write_backs() + L2.get_prefetches();
    }
    printf("q. memory traffic:             %d\n", memory_traffic);

}