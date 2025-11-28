package com.da.anomaliesinsightsmodule.controller;

import com.da.anomaliesinsightsmodule.dto.CreateMappingRequestDto;
import com.da.anomaliesinsightsmodule.dto.DocumentDto;
import com.da.anomaliesinsightsmodule.entity.IndexKbIdMapping;
import com.da.anomaliesinsightsmodule.service.InsightsService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.NoSuchElementException;

@RestController
@RequestMapping("/api/insights")
public class InsightsController {

    private final InsightsService insightsService;

    private final Logger logger = LoggerFactory.getLogger(InsightsController.class);

    public InsightsController(InsightsService insightsService) {
        this.insightsService = insightsService;
    }

    @GetMapping("/test")
    public ResponseEntity<String> getTest(){

        return ResponseEntity.ok("hello world");
    }

    @PostMapping("/mailTest")
    public ResponseEntity<String> mailTest(@RequestBody String to) throws Exception {

        insightsService.sendMailTest(to);
        return ResponseEntity.ok("correo enviado");
    }

    @PutMapping("/dashboards")
    public ResponseEntity createMapping(@RequestBody CreateMappingRequestDto kbIdMapping){

        try{

            insightsService.createKbMapping(new IndexKbIdMapping(
                    kbIdMapping.getKbId(),
                    kbIdMapping.getSourceIndex(),
                    null,  // anomalyIndex will be derived
                    null,
                    null,
                    null
            ));

            return ResponseEntity.ok(kbIdMapping.getKbId());

        }
        catch (IllegalArgumentException e){

            logger.error("Error creating mapping for kbId: {}", kbIdMapping.getKbId(), e);
            return ResponseEntity.status(409).body(e.getMessage());

        }
        catch (Exception e){

            logger.error("Error creating mapping for kbId: {}", kbIdMapping.getKbId(), e);
            return ResponseEntity.status(500).body("Internal Server Error creating mapping");

        }
    }

    @PostMapping("/dashboard/{kbId}/anomalies")
    public ResponseEntity insertDocument(@PathVariable String kbId, @RequestBody DocumentDto doc){

        try{

            insightsService.uploadDocument(kbId, doc);

            return ResponseEntity.ok(kbId);

        }catch (IllegalArgumentException e){

            logger.error("Document already exists: {}", kbId, e);
            return ResponseEntity.status(409).body(e.getMessage());

        }
        catch (NoSuchElementException e){

            logger.error("Mapping does not exists: {}", kbId, e);
            return ResponseEntity.status(404).body(e.getMessage());

        }
        catch (Exception e){

            logger.error("Error inserting document in ElasticSearch anomalies instance: {}", kbId, e);
            return ResponseEntity.status(500).body("Internal Server Error creating mapping");

        }

    }

}
