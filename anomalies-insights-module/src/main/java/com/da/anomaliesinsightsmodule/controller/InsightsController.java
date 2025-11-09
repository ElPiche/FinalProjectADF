package com.da.anomaliesinsightsmodule.controller;

import com.da.anomaliesinsightsmodule.dto.DocumentDto;
import com.da.anomaliesinsightsmodule.entity.IndexKbIdMapping;
import com.da.anomaliesinsightsmodule.service.InsightsService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/insights")
public class InsightsController {

    private final InsightsService insightsService;

    public InsightsController(InsightsService insightsService) {
        this.insightsService = insightsService;
    }

    @GetMapping("/test")
    public ResponseEntity<String> getTest(){

        return ResponseEntity.ok("hello world");
    }

    @PostMapping("/createMapping")
    public ResponseEntity createMapping(@RequestBody IndexKbIdMapping kbIdMapping){

        try{

            insightsService.createKbMapping(kbIdMapping);

            return ResponseEntity.ok(kbIdMapping.getKbId());

        }catch (Exception e){
            e.printStackTrace();
        }

        return null;
    }

    @PostMapping("/insertDocument/{kbId}")
    public ResponseEntity insertDocument(@PathVariable String kbId, @RequestBody DocumentDto doc){

        try{

            insightsService.uploadDocument(kbId, doc);

            return ResponseEntity.ok(kbId);

        }catch (Exception e){
            e.printStackTrace();
        }

        return null;
    }




}
