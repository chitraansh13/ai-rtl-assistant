`timescale 1ns/1ps

module fifo_sync_tb;
    parameter DATA_WIDTH = 8;
    parameter DEPTH = 16;
    parameter ADDR_WIDTH = $clog2(DEPTH);

    logic clk, rst, wr_en, rd_en;
    logic [DATA_WIDTH-1:0] data_in, data_out;
    logic full, empty;
    logic [ADDR_WIDTH:0] count;
    integer pass = 0;
    integer fail = 0;
    integer i;

    fifo_sync #(.DATA_WIDTH(DATA_WIDTH), .DEPTH(DEPTH)) dut (.*);

    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    initial begin
        $dumpfile("fifo_sync.vcd");
        $dumpvars(0, fifo_sync_tb);
    end

    initial begin
        rst = 1; wr_en = 0; rd_en = 0; data_in = 0;
        @(posedge clk); #1;
        if (empty && count == 0) begin $display("PASS : Reset"); pass++; end
        else begin $display("FAIL : Reset"); fail++; end
        rst = 0;

        data_in = 8'hAA; wr_en = 1;
        @(posedge clk); #1; wr_en = 0;
        if (count == 1 && !empty) begin $display("PASS : Single Write"); pass++; end
        else begin $display("FAIL : Single Write"); fail++; end

        rd_en = 1;
        @(posedge clk); #1; rd_en = 0;
        if (data_out == 8'hAA && empty && count == 0) begin $display("PASS : Single Read"); pass++; end
        else begin $display("FAIL : Single Read Expected=AA Got=%h", data_out); fail++; end

        wr_en = 1;
        // Drive the next item after the active clock edge to avoid a
        // testbench/DUT race at posedge clk.
        data_in = 8'h11; @(posedge clk); #1;
        data_in = 8'h22; @(posedge clk); #1;
        data_in = 8'h33; @(posedge clk); #1;
        wr_en = 0; rd_en = 1;
        @(posedge clk); #1;
        if (data_out == 8'h11) begin $display("PASS : FIFO Order Read1"); pass++; end
        else begin $display("FAIL : FIFO Order Read1 Expected=11 Got=%h", data_out); fail++; end
        @(posedge clk); #1;
        if (data_out == 8'h22) begin $display("PASS : FIFO Order Read2"); pass++; end
        else begin $display("FAIL : FIFO Order Read2 Expected=22 Got=%h", data_out); fail++; end
        @(posedge clk); #1; rd_en = 0;
        if (data_out == 8'h33) begin $display("PASS : FIFO Order Read3"); pass++; end
        else begin $display("FAIL : FIFO Order Read3 Expected=33 Got=%h", data_out); fail++; end

        rd_en = 1; @(posedge clk); #1; rd_en = 0;
        if (empty && count == 0) begin $display("PASS : Empty Behaviour"); pass++; end
        else begin $display("FAIL : Empty Behaviour"); fail++; end

        wr_en = 1;
        for (i = 0; i < DEPTH; i++) begin data_in = i; @(posedge clk); end
        #1; wr_en = 0;
        if (full && count == DEPTH) begin $display("PASS : Full Behaviour"); pass++; end
        else begin $display("FAIL : Full Behaviour"); fail++; end

        data_in = 8'hFF; wr_en = 1; @(posedge clk); #1; wr_en = 0;
        if (full && count == DEPTH) begin $display("PASS : Write While Full"); pass++; end
        else begin $display("FAIL : Write While Full"); fail++; end

        rd_en = 1; repeat (DEPTH) @(posedge clk); #1; rd_en = 0;
        if (empty && count == 0) begin $display("PASS : Pointer Wraparound"); pass++; end
        else begin $display("FAIL : Pointer Wraparound"); fail++; end

        wr_en = 1; data_in = 8'h55; @(posedge clk); #1;
        rd_en = 1; data_in = 8'hAA; @(posedge clk); #1; wr_en = 0; rd_en = 0;
        if (count == 1 && data_out == 8'h55) begin $display("PASS : Simultaneous Read/Write"); pass++; end
        else begin $display("FAIL : Simultaneous Read/Write"); fail++; end

        wr_en = 1; rd_en = 1; rst = 1; @(posedge clk); #1;
        rst = 0; wr_en = 0; rd_en = 0;
        if (empty && count == 0) begin $display("PASS : Reset Priority"); pass++; end
        else begin $display("FAIL : Reset Priority"); fail++; end

        $display("Tests Passed : %0d", pass);
        $display("Tests Failed : %0d", fail);
        if (fail == 0) $display("ALL TESTS PASSED");
        else $display("SOME TESTS FAILED");
        #20 $finish;
    end
endmodule